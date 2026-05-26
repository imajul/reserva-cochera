"""
Unit tests for reservar_cochera.py.
All Playwright and time-dependent behaviour is fully mocked.
"""

import re
import time as _time
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch, call

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


# ─── seleccionar_cochera ──────────────────────────────────────────────────────

class TestSeleccionarCochera:
    def test_primera_prioridad(self):
        # Prioridad actual: 208 → 237 → 238 (209 eliminada)
        cocheras = {208: "btn208", 237: "btn237", 238: "btn238"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 208
        assert elemento == "btn208"

    def test_segunda_prioridad(self):
        cocheras = {237: "btn237", 238: "btn238"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 237

    def test_tercera_prioridad(self):
        cocheras = {238: "btn238", 300: "btn300"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 238

    def test_cuarta_prioridad(self):
        # Sin ninguna prioritaria → fallback a la primera disponible
        cocheras = {300: "btn300", 100: "btn100"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 100

    def test_fallback_primera_disponible(self):
        cocheras = {300: "btn300", 100: "btn100", 400: "btn400"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 100
        assert elemento == "btn100"

    def test_dict_vacio_retorna_none(self):
        numero, elemento = rc.seleccionar_cochera({})
        assert numero is None
        assert elemento is None

    def test_unica_cochera_disponible(self):
        cocheras = {500: "btn500"}
        numero, elemento = rc.seleccionar_cochera(cocheras)
        assert numero == 500

    def test_no_modifica_el_dict_original(self):
        cocheras = {237: "btn237", 209: "btn209"}
        original = dict(cocheras)
        rc.seleccionar_cochera(cocheras)
        assert cocheras == original


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
        # 15:59:55 es después de pre_apertura (15:59:50) → no debe dormir
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
        # A las 15:00 debe esperar hasta 15:59:50 → 3590 segundos
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
                # Desde medianoche hasta 15:59:50 = 57590 segundos
                assert abs(segundos - 57590) < 2
