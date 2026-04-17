"""
Script de PRUEBA — Reserva real en Parkalot.
Flujo real:
  1. Login
  2. Click en DETAILS del día deseado
  3. En la pantalla del mapa, buscar la cochera en la lista derecha (scroll)
  4. Click en la cochera para seleccionarla
  5. Click en RESERVE
"""

import os
import sys
import logging
from datetime import date
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_URL = "https://app.parkalot.io/#/client"
EMAIL        = os.environ["PARKALOT_EMAIL"]
PASSWORD     = os.environ["PARKALOT_PASSWORD"]
TARGET_SPOT  = 209

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def encontrar_cochera_mas_cercana(spots: list[int]) -> int | None:
    if not spots:
        return None
    return min(spots, key=lambda x: abs(x - TARGET_SPOT))


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


def click_details_del_dia(page, fecha_str: str):
    """
    En la pantalla principal aparecen tarjetas por día.
    Busca la tarjeta que corresponde a la fecha y hace click en DETAILS.
    Si hay una sola tarjeta visible (hoy), hace click directo en DETAILS.
    """
    log.info(f"Buscando tarjeta del día {fecha_str} y haciendo click en DETAILS...")
    page.wait_for_timeout(1500)

    # Intentar encontrar DETAILS cerca del texto de la fecha
    # La app muestra "Friday 17th April" — buscamos por texto del día
    try:
        # Esperar a que la tarjeta del día cargue
        page.wait_for_selector("text=DETAILS", timeout=10000)
        # Hacer click en cualquier elemento que contenga el texto DETAILS
        page.get_by_text("DETAILS").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path="test_04_post_details.png")
        log.info("Click en DETAILS ✓")
    except PlaywrightTimeoutError:
        log.error("No se encontró el botón DETAILS")
        page.screenshot(path="test_error_no_details.png")
        raise


def seleccionar_y_reservar_cochera(page) -> bool:
    """
    En la pantalla del mapa:
    - Lista de cocheras a la derecha
    - Hacer scroll hasta encontrar TARGET_SPOT
    - Click en la cochera para seleccionarla
    - Click en RESERVE
    """
    log.info(f"Buscando cochera {TARGET_SPOT} en la lista...")
    page.wait_for_timeout(2000)
    page.screenshot(path="test_05_pantalla_mapa.png")

    cochera_seleccionada = None

    # La lista de cocheras está a la derecha — cada ítem muestra el número
    # Intentar encontrar directamente por texto exacto del número
    try:
        # Scroll dentro del panel derecho hasta encontrar la cochera
        # Parkalot muestra cada cochera como un ítem con su número
        cochera_item = page.locator(
            f"text='{TARGET_SPOT}'"
        ).first
        cochera_item.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        cochera_item.click()
        cochera_seleccionada = TARGET_SPOT
        log.info(f"Cochera {TARGET_SPOT} seleccionada ✓")
    except Exception:
        log.warning(f"No se encontró cochera {TARGET_SPOT}, buscando alternativa...")

    # Si no encontró la cochera objetivo, buscar la más cercana disponible
    if cochera_seleccionada is None:
        try:
            # Obtener todos los ítems de la lista de cocheras
            items = page.locator("text=/^\\d+$/").all()
            numeros = []
            for item in items:
                try:
                    n = int(item.inner_text().strip())
                    numeros.append((n, item))
                except ValueError:
                    continue

            if not numeros:
                log.error("No se encontraron cocheras en la lista.")
                page.screenshot(path="test_error_sin_cocheras.png")
                return False

            mejor = encontrar_cochera_mas_cercana([n for n, _ in numeros])
            log.info(f"Seleccionando cochera más cercana: {mejor}")
            for n, el in numeros:
                if n == mejor:
                    el.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    el.click()
                    cochera_seleccionada = mejor
                    break
        except Exception as e:
            log.error(f"Error buscando alternativa: {e}")
            page.screenshot(path="test_error_sin_cocheras.png")
            return False

    page.wait_for_timeout(1000)
    page.screenshot(path="test_06_cochera_seleccionada.png")

    # Click en RESERVE
    log.info("Haciendo click en RESERVE...")
    try:
        page.wait_for_selector("text=RESERVE", timeout=5000)
        page.get_by_text("RESERVE").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        log.error("No se encontró el botón RESERVE.")
        page.screenshot(path="test_error_sin_reserve.png")
        return False

    page.screenshot(path="test_07_resultado_final.png")
    log.info(f"✅ Reserva enviada — Cochera {cochera_seleccionada}")

    # Confirmar popup si aparece
    try:
        confirm = page.locator(
            "button:has-text('Confirm'), button:has-text('OK'), "
            "button:has-text('Yes'), button:has-text('Aceptar')"
        ).first
        confirm.wait_for(timeout=3000)
        confirm.click()
        page.wait_for_timeout(1500)
        page.screenshot(path="test_08_confirmacion_final.png")
        log.info("Confirmación adicional aceptada ✓")
    except PlaywrightTimeoutError:
        pass  # No siempre hay popup de confirmación

    return True


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata (sin espera de horario)")
    log.info("=" * 60)

    hoy = date.today()
    fecha_str = hoy.strftime("%Y-%m-%d")
    log.info(f"Reservando cochera {TARGET_SPOT} para: {fecha_str}")

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
            click_details_del_dia(page, fecha_str)
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
