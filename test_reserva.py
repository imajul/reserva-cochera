"""
Script de PRUEBA — Reserva real en Parkalot.
Reserva para HOY sin esperar las 16:00.
Orden de prioridad: 237 → 209 → 208 → 238 → primera disponible.
Siempre clickea el ÚLTIMO botón DETAILS (el del día siguiente).
"""

import os
import sys
import logging
from datetime import date
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

PARKALOT_URL       = "https://app.parkalot.io/#/client"
EMAIL              = os.environ["PARKALOT_EMAIL"]
PASSWORD           = os.environ["PARKALOT_PASSWORD"]
COCHERAS_PRIORIDAD = [237, 209, 208, 238]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def login(page):
    log.info("Navegando a Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="test_01_inicio.png")

    log.info("Iniciando sesión...")
    page.locator(
        "input[type='email'], input[name='email'], "
        "input[placeholder*='mail' i], input[formcontrolname='email']"
    ).first.fill(EMAIL)
    page.locator(
        "input[type='password'], input[formcontrolname='password']"
    ).first.fill(PASSWORD)
    page.screenshot(path="test_02_login.png")
    page.locator(
        "button:has-text('LOG IN'), button:has-text('Log in'), "
        "button:has-text('Login'), button:has-text('Ingresar'), button[type='submit']"
    ).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="test_03_post_login.png")
    log.info("Sesión iniciada ✓")


def click_details_del_dia(page):
    log.info("Buscando botones DETAILS...")
    page.wait_for_timeout(1500)
    page.wait_for_selector("text=DETAILS", timeout=10000)
    details_btns = page.get_by_text("DETAILS").all()
    log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
    # Siempre el último = día siguiente
    details_btns[-1].click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="test_04_post_details.png")
    log.info("Click en DETAILS del día siguiente ✓")


def seleccionar_y_reservar_cochera(page) -> bool:
    log.info("Obteniendo cocheras disponibles...")
    page.wait_for_timeout(2000)
    page.screenshot(path="test_05_pantalla_mapa.png")

    # Obtener todas las cocheras disponibles
    cocheras_disponibles = {}
    items = page.locator("button.MuiButtonBase-root:has(h6)").all()
    for item in items:
        try:
            n = int(item.locator("h6").inner_text().strip())
            cocheras_disponibles[n] = item
        except ValueError:
            continue

    if not cocheras_disponibles:
        log.error("No hay cocheras disponibles.")
        page.screenshot(path="test_error_sin_cocheras.png")
        return False

    log.info(f"Cocheras disponibles: {sorted(cocheras_disponibles.keys())}")

    # Seleccionar por orden de prioridad
    cochera_seleccionada = None
    elemento_seleccionado = None

    for cochera in COCHERAS_PRIORIDAD:
        if cochera in cocheras_disponibles:
            cochera_seleccionada = cochera
            elemento_seleccionado = cocheras_disponibles[cochera]
            log.info(f"Cochera preferida disponible: {cochera} ✓")
            break

    if cochera_seleccionada is None:
        primer_numero = sorted(cocheras_disponibles.keys())[0]
        cochera_seleccionada = primer_numero
        elemento_seleccionado = cocheras_disponibles[primer_numero]
        log.info(f"Ninguna preferida disponible. Reservando la primera: {primer_numero}")

    # Click en la cochera
    elemento_seleccionado.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    elemento_seleccionado.click()
    page.wait_for_timeout(1200)
    page.screenshot(path="test_06_cochera_seleccionada.png")
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
        page.screenshot(path="test_error_sin_reserve.png")
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

    page.screenshot(path="test_07_resultado_final.png")
    log.info(f"✅ Reserva exitosa — Cochera {cochera_seleccionada}")
    return True


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata (sin espera de horario)")
    log.info("=" * 60)

    fecha_str = date.today().strftime("%Y-%m-%d")
    log.info(f"Reservando para: {fecha_str}")
    log.info(f"Orden de prioridad: {COCHERAS_PRIORIDAD}")

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
            click_details_del_dia(page)
            exito = seleccionar_y_reservar_cochera(page)
            if not exito:
                log.error("❌ La reserva de prueba falló.")
                sys.exit(1)
        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            try:
                page.screenshot(path="test_error_inesperado.png")
            except Exception:
                pass
            sys.exit(1)
        finally:
            browser.close()

    log.info("Test finalizado.")


if __name__ == "__main__":
    main()
