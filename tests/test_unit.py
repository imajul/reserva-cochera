"""
Unit tests for reservar_cochera.py.
All Playwright and time-dependent behaviour is fully mocked.
"""

import re
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

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


# ─── debe_ejecutar_hoy ────────────────────────────────────────────────────────────────

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


# ─── fecha_manana_str ───────────────────────────────────────────────────────────────────

class TestFechaMáñanaStr:
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


# ─── esperar_hasta_previa_apertura ─────────────────────────────────────────────────────────────

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


# ─── enviar_whatsapp ──────────────────────────────────────────────────────────

class TestEnviarWhatsapp:
    def test_skip_cuando_no_hay_credenciales(self):
        with patch.object(rc, "WHATSAPP_PHONE", ""), \
             patch.object(rc, "WHATSAPP_APIKEY", ""), \
             patch("reservar_cochera.urllib.request.urlopen") as mock_urlopen:
            rc.enviar_whatsapp("test")
            mock_urlopen.assert_not_called()

    def test_llama_urlopen_cuando_hay_credenciales(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch.object(rc, "WHATSAPP_PHONE", "5491100000000"), \
             patch.object(rc, "WHATSAPP_APIKEY", "test-key"), \
             patch("reservar_cochera.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            rc.enviar_whatsapp("reserva ok")
            mock_urlopen.assert_called_once()
            url_llamado = mock_urlopen.call_args[0][0]
            assert "5491100000000" in url_llamado
            assert "test-key" in url_llamado

    def test_no_propaga_excepcion_en_error_de_red(self):
        with patch.object(rc, "WHATSAPP_PHONE", "5491100000000"), \
             patch.object(rc, "WHATSAPP_APIKEY", "test-key"), \
             patch("reservar_cochera.urllib.request.urlopen", side_effect=OSError("timeout")):
            rc.enviar_whatsapp("mensaje")  # no debe lanzar


# ─── _ordinal_en ──────────────────────────────────────────────────────────────

class TestOrdinalEn:
    @pytest.mark.parametrize("n,esperado", [
        (1,  "1ST"),
        (2,  "2ND"),
        (3,  "3RD"),
        (4,  "4TH"),
        (11, "11TH"),  # excepción th para 11
        (12, "12TH"),  # excepción th para 12
        (13, "13TH"),  # excepción th para 13
        (21, "21ST"),  # vuelve a st
        (22, "22ND"),
        (23, "23RD"),
    ])
    def test_sufijo_correcto(self, n, esperado):
        assert rc._ordinal_en(n) == esperado


# ─── screenshot ───────────────────────────────────────────────────────────────

class TestScreenshot:
    def test_llama_page_screenshot(self):
        mock_page = MagicMock()
        rc.screenshot(mock_page, "test_nombre")
        mock_page.screenshot.assert_called_once()
        _, kwargs = mock_page.screenshot.call_args
        assert "test_nombre" in kwargs["path"]
        assert kwargs["path"].endswith(".png")
        assert kwargs["full_page"] is True

    def test_path_incluye_contador_y_timestamp(self):
        mock_page = MagicMock()
        before = rc._screenshot_counter
        rc.screenshot(mock_page, "mi_paso")
        _, kwargs = mock_page.screenshot.call_args
        path = kwargs["path"]
        # formato: NNN_mi_paso_HHMMSSffffff.png (timestamp con microsegundos truncados a 6 chars)
        import re
        assert re.match(r"^\d{3}_mi_paso_\d{12}\.png$", path), f"path inesperado: {path}"
        assert rc._screenshot_counter == before + 1

    def test_no_propaga_excepcion_si_screenshot_falla(self):
        mock_page = MagicMock()
        mock_page.screenshot.side_effect = Exception("pantalla no disponible")
        rc.screenshot(mock_page, "test_fail")  # no debe lanzar
