"""
Script de PRUEBA — Reserva real en Parkalot.
Igual al script principal pero:
  - Saltea la espera hasta las 16:00
  - Saltea la validación de día hábil
  - Ejecuta inmediatamente el flujo completo y confirma la reserva
Usarlo para verificar que el sistema funciona correctamente.
"""

import os
import sys
import logging
from datetime import date, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_URL = "https://app.parkalot.io/#/client"
EMAIL        = os.environ["PARKALOT_EMAIL"]
PASSWORD     = os.environ["PARKALOT_PASSWORD"]
TARGET_SPOT  = 237

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
        "input[placeholder*='mail' i], input[formcontrolname='email'], "
        "input:near(:text('email'))"
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


def seleccionar_fecha(page, fecha_str: str):
    log.info(f"Seleccionando fecha: {fecha_str}")
    try:
        page.locator(
            "button:has-text('Nueva'), button:has-text('Reservar'), "
            "a:has-text('Nueva'), a:has-text('Reservar')"
        ).first.wait_for(timeout=3000)
        page.locator(
            "button:has-text('Nueva'), button:has-text('Reservar'), "
            "a:has-text('Nueva'), a:has-text('Reservar')"
        ).first.click()
        page.wait_for_timeout(1000)
    except PlaywrightTimeoutError:
        pass

    try:
        page.locator("input[type='date']").first.fill(fecha_str)
    except Exception:
        try:
            page.locator(f"text='{fecha_str}'").first.click()
        except Exception:
            pass

    page.wait_for_timeout(1500)
    page.screenshot(path="test_04_fecha_seleccionada.png")


def reservar(page, fecha_str: str) -> bool:
    seleccionar_fecha(page, fecha_str)
    page.wait_for_timeout(2000)

    log.info("Buscando cochera 237...")
    cochera_seleccionada = None

    for selector in [
        f"[data-spot='{TARGET_SPOT}']",
        f"[data-number='{TARGET_SPOT}']",
        f".spot:has-text('{TARGET_SPOT}')",
        f"text='{TARGET_SPOT}'",
    ]:
        try:
            el = page.locator(selector).first
            if not el.is_visible(timeout=1500):
                continue
            clases = el.get_attribute("class") or ""
            if "disabled" in clases or "occupied" in clases or el.get_attribute("disabled"):
                log.warning(f"Cochera {TARGET_SPOT} está ocupada.")
                break
            log.info(f"Cochera {TARGET_SPOT} disponible → seleccionando...")
            el.click()
            cochera_seleccionada = TARGET_SPOT
            break
        except PlaywrightTimeoutError:
            continue

    # Fallback: más cercana disponible
    if cochera_seleccionada is None:
        log.info("Buscando cochera alternativa más cercana a 237...")
        disponibles = []
        for spot in page.locator(
            ".spot:not(.disabled):not(.occupied), "
            ".parking-spot:not(.disabled):not(.occupied)"
        ).all():
            try:
                n = int(''.join(filter(str.isdigit, spot.inner_text().strip())))
                disponibles.append((n, spot))
            except ValueError:
                continue

        if not disponibles:
            log.error("No se encontraron cocheras disponibles.")
            page.screenshot(path="test_error_sin_cocheras.png")
            return False

        mejor = encontrar_cochera_mas_cercana([n for n, _ in disponibles])
        for n, el in disponibles:
            if n == mejor:
                log.info(f"Seleccionando cochera alternativa: {mejor}")
                el.click()
                cochera_seleccionada = mejor
                break

    page.wait_for_timeout(1000)
    page.screenshot(path="test_05_cochera_seleccionada.png")

    # Confirmar
    log.info("Confirmando reserva...")
    try:
        page.locator(
            "button:has-text('Confirmar'), button:has-text('Reservar'), "
            "button:has-text('Confirm'), button[type='submit']"
        ).last.wait_for(timeout=5000)
        page.locator(
            "button:has-text('Confirmar'), button:has-text('Reservar'), "
            "button:has-text('Confirm'), button[type='submit']"
        ).last.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        log.error("No se encontró botón de confirmación.")
        page.screenshot(path="test_error_sin_boton_confirmar.png")
        return False

    page.screenshot(path="test_06_resultado_final.png")

    try:
        page.locator(
            "text='confirmad', text='exitosa', text='success', text='reservad'"
        ).first.wait_for(timeout=5000)
    except PlaywrightTimeoutError:
        pass

    log.info(f"✅ Reserva exitosa — Cochera {cochera_seleccionada} para el {fecha_str}")
    return True


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata (sin espera de horario)")
    log.info("=" * 60)

    # Reservar para mañana (sin importar qué día sea)
    manana = date.today() + timedelta(days=1)
    # Si mañana es sábado, saltar al lunes
    if manana.weekday() == 5:
        manana += timedelta(days=2)
    elif manana.weekday() == 6:
        manana += timedelta(days=1)

    fecha_str = manana.strftime("%Y-%m-%d")
    log.info(f"Reservando para: {fecha_str}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires"
        )
        page = context.new_page()

        try:
            login(page)
            exito = reservar(page, fecha_str)
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
