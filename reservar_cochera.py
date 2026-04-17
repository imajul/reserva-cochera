"""
Automatización de reserva de cochera en Parkalot.
Flujo real:
  1. Arranca a las 15:55 ARG y espera hasta las 16:00
  2. Login
  3. Click en DETAILS del día siguiente
  4. En el mapa, buscar cochera 209 en la lista derecha (scroll)
  5. Click en la cochera → Click en RESERVE
  Si la 209 está ocupada, reserva la más cercana disponible.
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
TARGET_SPOT     = 209
DIAS_RESERVA    = {0, 1, 2, 4}   # Lunes=0, Martes=1, Miércoles=2, Viernes=4
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

def dia_siguiente_es_habil() -> bool:
    manana_weekday = (date.today().weekday() + 1) % 7
    return manana_weekday in DIAS_RESERVA

def fecha_manana_str() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

def encontrar_cochera_mas_cercana(spots: list[int]) -> int | None:
    if not spots:
        return None
    return min(spots, key=lambda x: abs(x - TARGET_SPOT))

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
    """Hace click en DETAILS de la tarjeta del día siguiente."""
    log.info("Buscando botón DETAILS...")
    page.wait_for_timeout(1500)
    try:
        page.wait_for_selector("text=DETAILS", timeout=8000)
        page.get_by_text("DETAILS").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        log.info("Click en DETAILS ✓")
        return True
    except PlaywrightTimeoutError:
        log.warning("No se encontró el botón DETAILS — las reservas aún no están habilitadas.")
        return False


def seleccionar_y_reservar_cochera(page) -> bool:
    """Busca la cochera en la lista derecha, la selecciona y presiona RESERVE."""
    log.info(f"Buscando cochera {TARGET_SPOT} en la lista...")
    page.wait_for_timeout(2000)

    cochera_seleccionada = None

    # Buscar cochera objetivo por número exacto en la lista
    try:
        cochera_item = page.locator(f"text='{TARGET_SPOT}'").first
        cochera_item.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        cochera_item.click()
        cochera_seleccionada = TARGET_SPOT
        log.info(f"Cochera {TARGET_SPOT} seleccionada ✓")
    except Exception:
        log.warning(f"Cochera {TARGET_SPOT} no disponible, buscando alternativa...")

    # Fallback: cochera más cercana
    if cochera_seleccionada is None:
        try:
            items = page.locator("text=/^\\d+$/").all()
            numeros = []
            for item in items:
                try:
                    n = int(item.inner_text().strip())
                    numeros.append((n, item))
                except ValueError:
                    continue

            if not numeros:
                log.warning("No hay cocheras disponibles en la lista.")
                return False

            mejor = encontrar_cochera_mas_cercana([n for n, _ in numeros])
            log.info(f"Reservando cochera más cercana: {mejor}")
            for n, el in numeros:
                if n == mejor:
                    el.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    el.click()
                    cochera_seleccionada = mejor
                    break
        except Exception as e:
            log.error(f"Error buscando alternativa: {e}")
            return False

    page.wait_for_timeout(1000)

    # Click en RESERVE
    log.info("Haciendo click en RESERVE...")
    try:
        page.wait_for_selector("text=RESERVE", timeout=5000)
        page.get_by_text("RESERVE").first.click()
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

    if not dia_siguiente_es_habil():
        log.info("El día siguiente no requiere reserva. Finalizando.")
        sys.exit(0)

    manana = date.today() + timedelta(days=1)
    if manana.weekday() >= 5:
        log.info("El día siguiente es fin de semana. Finalizando.")
        sys.exit(0)

    log.info(f"Objetivo: reservar cochera {TARGET_SPOT} para el {fecha_manana_str()}")
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

                    details_ok = click_details_del_dia(page)
                    if not details_ok:
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
