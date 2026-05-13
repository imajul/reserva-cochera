"""
Script de PRUEBA — Reserva real en Parkalot.
Reserva para HOY sin esperar las 16:00.
Orden de prioridad: 237 → 209 → 208 → 238 → primera disponible.
"""

import sys
import logging
from playwright.sync_api import sync_playwright

from reservar_cochera import (
    PARKALOT_URL, COCHERAS_PRIORIDAD,
    login, click_details_del_dia, seleccionar_y_reservar_cochera,
    fecha_manana_str, enviar_whatsapp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata (sin espera de horario)")
    log.info("=" * 60)
    log.info(f"Reservando para: {fecha_manana_str()}")
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
            enviar_whatsapp(f"🧪 Test de notificación activo — reserva para el {fecha_manana_str()}")
            login(page)
            page.screenshot(path="test_01_post_login.png")

            if not click_details_del_dia(page):
                log.error("❌ No se encontró el botón DETAILS.")
                log.error("   Posibles causas:")
                log.error("   - Las reservas aún no están habilitadas (ejecutar cerca de las 16:00)")
                log.error("   - La sesión no se inició correctamente")
                page.screenshot(path="test_02_sin_details.png")
                sys.exit(1)

            page.screenshot(path="test_02_post_details.png")

            exito = seleccionar_y_reservar_cochera(page)
            if not exito:
                log.error("❌ La reserva de prueba falló — todas las cocheras ocupadas.")
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

    log.info("✅ Test finalizado correctamente.")


if __name__ == "__main__":
    main()
