"""
Automatización de reserva de cochera en Parkalot.
Flujo:
  1. Arranca a las 15:55 ARG y espera hasta las 16:00
  2. Login
  3. Click en el SEGUNDO botón DETAILS (el del día siguiente)
  4. En el mapa, buscar cochera según orden de prioridad
  5. Click en la cochera → Click en RESERVE

Días de ejecución: domingo, lunes, martes y jueves (para reservar el día siguiente).
Orden de prioridad: 237 → 209 → 208 → 238 → primera disponible en la lista.
"""

import os
import sys
import time
import logging
from datetime import datetime, date, timedelta
import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_URL    = "https://app.parkalot.io/#/client"
EMAIL           = os.environ["PARKALOT_EMAIL"]
PASSWORD        = os.environ["PARKALOT_PASSWORD"]

# Orden de prioridad de cocheras
COCHERAS_PRIORIDAD = [237, 209, 208, 238]

# Días en que corre el script (para reservar el día siguiente hábil)
# Domingo=6, Lunes=0, Martes=1, Jueves=3
DIAS_EJECUCION  = {6, 0, 1, 3}

TZ_ARG          = pytz.timezone("America/Argentina/Buenos_Aires")
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
INTERVALO_REINTENTO_SEG = 5
TIMEOUT_ESPERA_MIN = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def ahora_arg() -> datetime:
    return datetime.now(TZ_ARG)

def debe_ejecutar_hoy() -> bool:
    return date.today().weekday() in DIAS_EJECUCION

def fecha_manana_str() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

def esperar_hasta_previa_apertura():
    ahora = ahora_arg()
    apertura = ahora.replace(hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0)
    pre_apertura = apertura - timedelta(seconds=10)
    if ahora < pre_apertura:
        espera_seg = (pre_apertura - ahora).total_seconds()
        log.info(f"Son las {ahora.strftime('%H:%M:%S')} ARG. Esperando hasta las 15:59:50 ({int(espera_seg)}s)...")
        time.sleep(espera_seg)
    log.info("Entrando en modo de espera activa...")


def login(page):
    log.info("Navegando a Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)

    log.info("Iniciando sesión...")
    page.locator(
        "input[type='email'], input[name='email'], "
        "input[placeholder*='mail' i], input[formcontrolname='email']"
    ).first.fill(EMAIL)
    page.locator(
        "input[type='password'], input[formcontrolname='password']"
    ).first.fill(PASSWORD)
    page.locator(
        "button:has-text('LOG IN'), button:has-text('Log in'), "
        "button:has-text('Login'), button:has-text('Ingresar'), button[type='submit']"
    ).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    log.info("Sesión iniciada ✓")


def click_details_del_dia(page) -> bool:
    """
    Hace click en el SEGUNDO botón DETAILS (el del día siguiente).
    Cuando hay dos tarjetas visibles, la primera es el día de hoy
    y la segunda es el día siguiente.
    """
    log.info("Buscando botones DETAILS...")
    page.wait_for_timeout(1500)
    try:
        page.wait_for_selector("text=DETAILS", timeout=8000)
        details_btns = page.get_by_text("DETAILS").all()
        log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
        # Siempre clickear el último (el del día siguiente)
        details_btns[-1].click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        log.info("Click en DETAILS del día siguiente ✓")
        return True
    except PlaywrightTimeoutError:
        log.warning("No se encontró el botón DETAILS — las reservas aún no están habilitadas.")
        return False


def seleccionar_y_reservar_cochera(page) -> bool:
    """
    Busca la cochera según orden de prioridad: 237 → 209 → 208 → 238 → primera disponible.
    """
    log.info("Obteniendo cocheras disponibles en la lista...")
    page.wait_for_timeout(2000)

    # Obtener todas las cocheras disponibles en la lista
    cocheras_disponibles = {}
    try:
        items = page.locator("button.MuiButtonBase-root:has(h6)").all()
        for item in items:
            try:
                n = int(item.locator("h6").inner_text().strip())
                cocheras_disponibles[n] = item
            except ValueError:
                continue
    except Exception as e:
        log.error(f"Error obteniendo lista de cocheras: {e}")
        return False

    if not cocheras_disponibles:
        log.warning("No hay cocheras disponibles en la lista.")
        return False

    log.info(f"Cocheras disponibles: {sorted(cocheras_disponibles.keys())}")

    # Seleccionar según orden de prioridad
    cochera_seleccionada = None
    elemento_seleccionado = None

    for cochera in COCHERAS_PRIORIDAD:
        if cochera in cocheras_disponibles:
            cochera_seleccionada = cochera
            elemento_seleccionado = cocheras_disponibles[cochera]
            log.info(f"Cochera preferida disponible: {cochera} ✓")
            break

    # Si ninguna de las preferidas está disponible, tomar la primera de la lista
    if cochera_seleccionada is None:
        primer_numero = sorted(cocheras_disponibles.keys())[0]
        cochera_seleccionada = primer_numero
        elemento_seleccionado = cocheras_disponibles[primer_numero]
        log.info(f"Ninguna cochera preferida disponible. Reservando la primera: {primer_numero}")

    # Click en la cochera seleccionada
    elemento_seleccionado.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    elemento_seleccionado.click()
    page.wait_for_timeout(1200)
    log.info(f"Cochera {cochera_seleccionada} seleccionada ✓")

    # Click en RESERVE
    log.info("Haciendo click en RESERVE...")
    try:
        reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
        reserve_btn.wait_for(timeout=5000)
        reserve_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        log.error("No se encontró el botón RESERVE.")
        return False

    # Confirmar popup si aparece
    try:
        confirm = page.locator(
            "button:has-text('Confirm'), button:has-text('OK'), "
            "button:has-text('Yes'), button:has-text('Aceptar')"
        ).first
        confirm.wait_for(timeout=3000)
        confirm.click()
        page.wait_for_timeout(1500)
        log.info("Confirmación adicional aceptada ✓")
    except PlaywrightTimeoutError:
        pass

    page.screenshot(path="resultado_reserva.png")
    log.info(f"✅ Reserva exitosa — Cochera {cochera_seleccionada}")
    return True


def main():
    log.info("=" * 60)
    log.info("  Reserva automática de cochera — Parkalot")
    log.info("=" * 60)

    if not debe_ejecutar_hoy():
        log.info(f"Hoy ({date.today().strftime('%A')}) no corresponde ejecutar. Finalizando.")
        sys.exit(0)

    log.info(f"Objetivo: reservar cochera para el {fecha_manana_str()}")
    log.info(f"Orden de prioridad: {COCHERAS_PRIORIDAD}")
    esperar_hasta_previa_apertura()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires"
        )
        page = context.new_page()

        try:
            login(page)

            apertura_arg = ahora_arg().replace(
                hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
            )
            limite = apertura_arg + timedelta(minutes=TIMEOUT_ESPERA_MIN)
            reservado = False
            intentos = 0

            while ahora_arg() <= limite:
                intentos += 1
                log.info(f"[Intento #{intentos} — {ahora_arg().strftime('%H:%M:%S')} ARG]")

                try:
                    page.reload(wait_until="networkidle")
                    page.wait_for_timeout(1500)

                    if not click_details_del_dia(page):
                        log.info(f"Reintentando en {INTERVALO_REINTENTO_SEG}s...")
                        time.sleep(INTERVALO_REINTENTO_SEG)
                        continue

                    reservado = seleccionar_y_reservar_cochera(page)
                except Exception as e:
                    log.warning(f"Error en intento #{intentos}: {e}")

                if reservado:
                    break

                log.info(f"Reintentando en {INTERVALO_REINTENTO_SEG}s...")
                time.sleep(INTERVALO_REINTENTO_SEG)

            if not reservado:
                log.error(f"❌ No se pudo reservar luego de {intentos} intentos.")
                page.screenshot(path="error_reserva.png")
                sys.exit(1)

        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            try:
                page.screenshot(path="error_reserva.png")
            except Exception:
                pass
            sys.exit(1)
        finally:
            browser.close()

    log.info("Script finalizado correctamente.")


if __name__ == "__main__":
    main()
