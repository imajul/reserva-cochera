"""
Script de PRUEBA — Reserva real en Parkalot via Playwright.
Reserva la cochera 238 para HOY de inmediato, sin esperar las 16:00.
"""

import sys
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from reservar_cochera import (
    PARKALOT_URL, EMAIL, PASSWORD,
    login, screenshot, seleccionar_y_reservar_cochera,
    enviar_whatsapp, ahora_arg,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

COCHERA_TEST = 238
COCHERAS_SOLO_238 = [238]


def main():
    fecha_hoy = ahora_arg().date().isoformat()
    log.info("=" * 60)
    log.info("  TEST — Reserva inmediata cochera 238 para HOY")
    log.info("=" * 60)
    log.info(f"Fecha: {fecha_hoy} (HOY)")

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

            # Buscar botón DETAILS de HOY (primero disponible)
            log.info("Buscando botón DETAILS para HOY...")
            page.wait_for_timeout(300)
            try:
                page.wait_for_selector("text=DETAILS", timeout=10000)
                details_btns = page.get_by_text("DETAILS").all()
                log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
                details_btns[0].click()  # primer botón = HOY
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(500)
                screenshot(page, "test_post_details")
                log.info("Click en DETAILS (HOY) ✓")
            except PlaywrightTimeoutError:
                log.error("❌ No se encontró el botón DETAILS.")
                screenshot(page, "test_sin_details")
                sys.exit(1)

            # Parchear temporalmente la lista de prioridad para solo intentar 238
            import reservar_cochera as rc
            original = rc.COCHERAS_PRIORIDAD
            rc.COCHERAS_PRIORIDAD = COCHERAS_SOLO_238
            try:
                reservado = seleccionar_y_reservar_cochera(page, intento=1)
            finally:
                rc.COCHERAS_PRIORIDAD = original

            if reservado:
                log.info(f"✅ Cochera {COCHERA_TEST} reservada para {fecha_hoy}")
                enviar_whatsapp(f"✅ [TEST] Cochera {COCHERA_TEST} reservada para hoy {fecha_hoy} 🚗")
            else:
                log.error(f"❌ No se pudo reservar cochera {COCHERA_TEST} — ocupada o no disponible.")
                enviar_whatsapp(f"❌ [TEST] Cochera {COCHERA_TEST} no disponible para hoy {fecha_hoy}.")
                sys.exit(1)

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
