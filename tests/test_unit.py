"""
Unit tests for reservar_cochera.py.
All HTTP calls and time-dependent behaviour are fully mocked.
"""

import re
import time as _time
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz

import reservar_cochera as rc


# ─── ahora_arg ────────────────────────────────────────────────────────────────

class TestAhoraArg:
    def test_returns_aware_datetime(self):
        result = rc.ahora_arg()
        assert result.tzinfo is not None

    def test_timezone_is_argentina(self):
        result = rc.ahora_arg()
        assert "Argentina" in str(result.tzinfo)


# ─── debe_ejecutar_hoy ────────────────────────────────────────────────────────

class TestDebeEjecutarHoy:
    TZ = pytz.timezone("America/Argentina/Buenos_Aires")

    def _dt(self, fecha):
        return datetime(fecha.year, fecha.month, fecha.day, 12, 0, 0, tzinfo=self.TZ)

    @pytest.mark.parametrize("fecha,esperado", [
        (date(2024, 3, 18), True),   # lunes      (0)
        (date(2024, 3, 19), True),   # martes     (1)
        (date(2024, 3, 20), True),   # miércoles  (2)
        (date(2024, 3, 21), True),   # jueves     (3)
        (date(2024, 3, 22), False),  # viernes    (4)
        (date(2024, 3, 23), False),  # sábado     (5)
        (date(2024, 3, 24), True),   # domingo    (6)
    ])
    def test_dias_ejecucion(self, fecha, esperado):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(fecha)):
            assert rc.debe_ejecutar_hoy() == esperado


# ─── fecha_manana_str ─────────────────────────────────────────────────────────

class TestFechaMañanaStr:
    TZ = pytz.timezone("America/Argentina/Buenos_Aires")

    def _dt(self, year, month, day):
        return datetime(year, month, day, 12, 0, 0, tzinfo=self.TZ)

    def test_formato_yyyy_mm_dd(self):
        result = rc.fecha_manana_str()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result)

    def test_es_manana(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(2024, 3, 15)):
            assert rc.fecha_manana_str() == "2024-03-16"

    def test_cruce_de_mes(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(2024, 1, 31)):
            assert rc.fecha_manana_str() == "2024-02-01"

    def test_cruce_de_ano(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(2023, 12, 31)):
            assert rc.fecha_manana_str() == "2024-01-01"


# ─── esperar_hasta_previa_apertura ────────────────────────────────────────────

class TestEsperarHastaPreApertura:
    TZ = pytz.timezone("America/Argentina/Buenos_Aires")

    def _dt(self, h, m, s=0):
        return datetime(2024, 3, 15, h, m, s, tzinfo=self.TZ)

    def test_no_duerme_cuando_ya_paso_apertura(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(16, 5)):
            with patch("reservar_cochera.time") as mock_time:
                rc.esperar_hasta_previa_apertura()
                mock_time.sleep.assert_not_called()

    def test_no_duerme_en_la_ventana_activa(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(15, 59, 55)):
            with patch("reservar_cochera.time") as mock_time:
                rc.esperar_hasta_previa_apertura()
                mock_time.sleep.assert_not_called()

    def test_duerme_cuando_es_antes_de_apertura(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(15, 0)):
            with patch("reservar_cochera.time") as mock_time:
                rc.esperar_hasta_previa_apertura()
                mock_time.sleep.assert_called_once()

    def test_duracion_correcta_del_sleep(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(15, 0)):
            with patch("reservar_cochera.time") as mock_time:
                rc.esperar_hasta_previa_apertura()
                segundos = mock_time.sleep.call_args[0][0]
                assert abs(segundos - 3590) < 2

    def test_duerme_desde_madrugada(self):
        with patch("reservar_cochera.ahora_arg", return_value=self._dt(0, 0)):
            with patch("reservar_cochera.time") as mock_time:
                rc.esperar_hasta_previa_apertura()
                mock_time.sleep.assert_called_once()
                segundos = mock_time.sleep.call_args[0][0]
                assert abs(segundos - 57590) < 2


# ─── renovar_token ────────────────────────────────────────────────────────────

class TestRenovarToken:
    def _mock_resp(self, status_code, json_data=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        return resp

    def test_retorna_id_token_en_200(self):
        resp = self._mock_resp(200, {"id_token": "token-fresco-abc123"})
        with patch("reservar_cochera.httpx.post", return_value=resp):
            token = rc.renovar_token("refresh-tok", "api-key-123")
        assert token == "token-fresco-abc123"

    def test_llama_endpoint_correcto(self):
        resp = self._mock_resp(200, {"id_token": "tok"})
        with patch("reservar_cochera.httpx.post", return_value=resp) as mock_post:
            rc.renovar_token("my-refresh", "my-api-key")
        url = mock_post.call_args[0][0]
        assert "securetoken.googleapis.com" in url
        assert "my-api-key" in url
        data = mock_post.call_args[1]["data"]
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "my-refresh"

    def test_lanza_error_en_400(self):
        resp = self._mock_resp(400, text="TOKEN_EXPIRED")
        with patch("reservar_cochera.httpx.post", return_value=resp):
            with pytest.raises(RuntimeError, match="400"):
                rc.renovar_token("bad-token", "api-key")

    def test_lanza_error_si_falta_id_token(self):
        resp = self._mock_resp(200, json_data={"refresh_token": "algo"})
        with patch("reservar_cochera.httpx.post", return_value=resp):
            with pytest.raises(RuntimeError, match="id_token"):
                rc.renovar_token("tok", "key")


# ─── reservar_via_api ─────────────────────────────────────────────────────────

class TestReservarViaApi:
    def _mock_resp(self, status_code, text="ok"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        return resp

    def test_retorna_true_en_200(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(200)):
            assert rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc") is True

    def test_retorna_true_en_201(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(201)):
            assert rc.reservar_via_api("tok", 208, "2026-06-04", "uid-abc") is True

    def test_retorna_false_en_409_spot_ocupado(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(409)):
            assert rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc") is False

    def test_retorna_false_en_403(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(403)):
            assert rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc") is False

    def test_lanza_error_en_401(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(401)):
            with pytest.raises(rc.TokenInvalidoError):
                rc.reservar_via_api("tok-invalido", 209, "2026-06-04", "uid-abc")

    def test_reintenta_una_vez_en_500_y_retorna_true(self):
        responses = [self._mock_resp(500), self._mock_resp(200)]
        with patch("reservar_cochera.httpx.post", side_effect=responses):
            with patch("reservar_cochera.time"):
                assert rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc") is True

    def test_lanza_error_en_500_persistente(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(503, "service unavailable")):
            with patch("reservar_cochera.time"):
                with pytest.raises(RuntimeError, match="503"):
                    rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc")

    def test_lanza_error_en_respuesta_inesperada(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(422, "unprocessable")):
            with pytest.raises(RuntimeError, match="422"):
                rc.reservar_via_api("tok", 209, "2026-06-04", "uid-abc")

    def test_payload_correcto(self):
        with patch("reservar_cochera.httpx.post", return_value=self._mock_resp(200)) as mock_post:
            rc.reservar_via_api("mi-token", 209, "2026-06-04", "mi-uid")
        kwargs = mock_post.call_args[1]
        assert kwargs["json"]["day"] == "2026-06-04"
        assert kwargs["json"]["spotId"] == 209
        assert kwargs["json"]["shifts"] == ["00002400"]
        assert kwargs["json"]["uid"] == "mi-uid"
        assert kwargs["headers"]["Authorization"] == "Bearer mi-token"
