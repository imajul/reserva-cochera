"""
Script de PRUEBA — Reserva real en Parkalot via Playwright.
Reserva la cochera 2054 para HOY de inmediato, usando las mismas
funciones del script principal (_buscar_y_clickear_cochera, etc.).
"""

import sys
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from reservar_cochera import (
    PARKALOT_URL,
    login, screenshot, enviar_whatsapp, ahora_arg, fecha_manana_str,
    _buscar_y_clickear_cochera,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

COCHERA_TEST = 2054


def main():
    fecha_hoy = ahora_arg().date().isoformat()
    log.info("=" * 60)
    log.info(f"  TEST — Reserva inmediata cochera {COCHERA_TEST} para HOY")
    log.info("=" * 60)
    log.info(f"Fecha objetivo: {fecha_hoy}")

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

            # Clickear el primer botón DETAILS disponible (= HOY)
            log.info("Buscando botón DETAILS...")
            try:
                page.wait_for_selector("text=DETAILS", timeout=10000)
                details_btns = page.get_by_text("DETAILS").all()
                log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
                if not details_btns:
                    log.error("❌ No hay botones DETAILS disponibles.")
                    sys.exit(1)
                details_btns[0].click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(800)
                screenshot(page, "test_post_details")
                log.info("Click en DETAILS ✓")
            except PlaywrightTimeoutError:
                log.error("❌ No se encontró el botón DETAILS.")
                screenshot(page, "test_sin_details")
                sys.exit(1)

            # Buscar y clickear cochera 2054 usando el nuevo selector
            log.info(f"Buscando cochera {COCHERA_TEST} en el sidebar...")
            screenshot(page, "test_pre_click")
            encontrada = _buscar_y_clickear_cochera(page, COCHERA_TEST)

            if not encontrada:
                log.error(f"❌ Cochera {COCHERA_TEST} no encontrada en el sidebar.")
                screenshot(page, "test_no_encontrada")
                sys.exit(1)

            log.info(f"Cochera {COCHERA_TEST} clickeada ✓")
            screenshot(page, "test_post_click")

            # Intentar reservar
            reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
            try:
                reserve_btn.wait_for(timeout=5000)
            except PlaywrightTimeoutError:
                log.error("❌ Botón RESERVE no encontrado.")
                screenshot(page, "test_sin_reserve")
                sys.exit(1)

            if not reserve_btn.is_enabled():
                log.error(f"❌ Cochera {COCHERA_TEST} tiene RESERVE deshabilitado — no disponible.")
                screenshot(page, "test_reserve_disabled")
                sys.exit(1)

            log.info("Botón RESERVE habilitado — reservando...")
            screenshot(page, "test_pre_reserve")
            reserve_btn.click()
            page.wait_for_timeout(3000)
            screenshot(page, "test_post_reserve")

            # Confirmar si hay diálogo
            try:
                confirm = page.locator(
                    "button:has-text('Confirm'), button:has-text('OK'), "
                    "button:has-text('Yes'), button:has-text('Aceptar')"
                ).first
                confirm.wait_for(timeout=3000)
                confirm.click()
                page.wait_for_timeout(1500)
                screenshot(page, "test_confirmacion")
                log.info("Confirmación aceptada ✓")
            except PlaywrightTimeoutError:
                pass

            screenshot(page, "test_resultado")
            log.info(f"✅ Cochera {COCHERA_TEST} reservada para {fecha_hoy}")
            enviar_whatsapp(f"✅ [TEST] Cochera {COCHERA_TEST} reservada para hoy {fecha_hoy} 🚗")

        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            try:
                screenshot(page, "test_error")
            except Exception:
                pass
            sys.exit(1)
        finally:
            browser.close()

    log.info("✅ Test finalizado correctamente.")


if __name__ == "__main__":
    main()
