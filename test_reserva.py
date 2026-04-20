"""
Script de PRUEBA — Reserva real en Parkalot.
Reserva para HOY sin esperar las 16:00.
Orden de prioridad: 237 → 209 → 208 → 238 → primera disponible.
"""

import sys
import logging
from datetime import date
from playwright.sync_api import sync_playwright

from reservar_cochera import (
    PARKALOT_URL, COCHERAS_PRIORIDAD,
    login, click_details_del_dia, seleccionar_y_reservar_cochera,
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
    log.info(f"Reservando para: {date.today().strftime('%Y-%m-%d')}")
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
            page.screenshot(path="test_01_post_login.png")

            click_details_del_dia(page)
            page.screenshot(path="test_02_post_details.png")

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
