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
from datetime import datetime, timedelta
import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_URL    = "https://app.parkalot.io/#/client"
EMAIL           = os.environ.get("PARKALOT_EMAIL", "")
PASSWORD        = os.environ.get("PARKALOT_PASSWORD", "")

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
    return ahora_arg().date().weekday() in DIAS_EJECUCION

def fecha_manana_str() -> str:
    return (ahora_arg().date() + timedelta(days=1)).strftime("%Y-%m-%d")

def esperar_hasta_previa_apertura():
    ahora = ahora_arg()
    apertura = ahora.replace(hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0)
    pre_apertura = apertura - timedelta(seconds=10)
    if ahora < pre_apertura:
        espera_seg = (pre_apertura - ahora).total_seconds()
        log.info(f"Son las {ahora.strftime('%H:%M:%S')} ARG. Esperando hasta las 15:59:50 ({int(espera_seg)}s)...")
        time.sleep(espera_seg)
    log.info("Entrando en modo de espera activa...")

def screenshot(page, nombre: str):
    path = f"{nombre}.png"
    try:
        page.screenshot(path=path, full_page=True)
        log.info(f"📸 Screenshot: {path}")
    except Exception as e:
        log.warning(f"No se pudo guardar screenshot {path}: {e}")


def login(page):
    log.info("Navegando a Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "01_login_form")

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
    screenshot(page, "02_post_login")
    log.info("Sesión iniciada ✓")


def click_details_del_dia(page, intento: int = 0) -> bool:
    """
    Hace click en el SEGUNDO botón DETAILS (el del día siguiente).
    Cuando hay dos tarjetas visibles, la primera es el día de hoy
    y la segunda es el día siguiente.
    """
    prefix = f"intento_{intento:02d}"
    log.info("Buscando botones DETAILS...")
    page.wait_for_timeout(1500)
    try:
        page.wait_for_selector("text=DETAILS", timeout=8000)
        details_btns = page.get_by_text("DETAILS").all()
        log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
        screenshot(page, f"{prefix}_details_encontrado")
        # Siempre clickear el último (el del día siguiente)
        details_btns[-1].click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, f"{prefix}_post_details")
        log.info("Click en DETAILS del día siguiente ✓")
        return True
    except PlaywrightTimeoutError:
        log.warning("No se encontró el botón DETAILS — las reservas aún no están habilitadas.")
        screenshot(page, f"{prefix}_sin_details")
        return False


def seleccionar_cochera(cocheras_disponibles: dict):
    """
    Elige la cochera según orden de prioridad.
    Retorna (numero, elemento) o (None, None) si el dict está vacío.
    """
    if not cocheras_disponibles:
        return None, None

    for cochera in COCHERAS_PRIORIDAD:
        if cochera in cocheras_disponibles:
            log.info(f"Cochera preferida disponible: {cochera} ✓")
            return cochera, cocheras_disponibles[cochera]

    primer_numero = sorted(cocheras_disponibles.keys())[0]
    log.info(f"Ninguna cochera preferida disponible. Reservando la primera: {primer_numero}")
    return primer_numero, cocheras_disponibles[primer_numero]


def seleccionar_y_reservar_cochera(page, intento: int = 0) -> bool:
    """
    Busca la cochera según orden de prioridad: 237 → 209 → 208 → 238 → primera disponible.
    """
    prefix = f"intento_{intento:02d}"
    log.info("Obteniendo cocheras disponibles en la lista...")
    page.wait_for_timeout(2000)
    screenshot(page, f"{prefix}_mapa")

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
        screenshot(page, f"{prefix}_error_lista")
        return False

    if not cocheras_disponibles:
        log.warning("No hay cocheras disponibles en la lista.")
        screenshot(page, f"{prefix}_sin_cocheras")
        return False

    log.info(f"Cocheras disponibles: {sorted(cocheras_disponibles.keys())}")

    cochera_seleccionada, elemento_seleccionado = seleccionar_cochera(cocheras_disponibles)

    # Click en la cochera seleccionada
    elemento_seleccionado.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    elemento_seleccionado.click()
    page.wait_for_timeout(1200)
    screenshot(page, f"{prefix}_cochera_seleccionada")
    log.info(f"Cochera {cochera_seleccionada} seleccionada ✓")

    # Click en RESERVE
    log.info("Haciendo click en RESERVE...")
    try:
        reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
        reserve_btn.wait_for(timeout=5000)
        screenshot(page, f"{prefix}_pre_reserve")
        reserve_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, f"{prefix}_post_reserve")
    except PlaywrightTimeoutError:
        log.error("No se encontró el botón RESERVE.")
        screenshot(page, f"{prefix}_sin_reserve")
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
        screenshot(page, f"{prefix}_confirmacion")
        log.info("Confirmación adicional aceptada ✓")
    except PlaywrightTimeoutError:
        pass

    screenshot(page, "resultado_reserva")
    log.info(f"✅ Reserva exitosa — Cochera {cochera_seleccionada}")
    return True


def main():
    log.info("=" * 60)
    log.info("  Reserva automática de cochera — Parkalot")
    log.info("=" * 60)

    ahora = ahora_arg()
    log.info(f"Hora actual ARG: {ahora.strftime('%A %Y-%m-%d %H:%M:%S')}")

    if not debe_ejecutar_hoy():
        log.info(f"Hoy ({ahora.strftime('%A')}) no corresponde ejecutar. Finalizando.")
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

            limite = ahora_arg() + timedelta(minutes=TIMEOUT_ESPERA_MIN)
            reservado = False
            intentos = 0

            while ahora_arg() <= limite:
                intentos += 1
                log.info(f"[Intento #{intentos} — {ahora_arg().strftime('%H:%M:%S')} ARG]")

                try:
                    page.reload(wait_until="networkidle")
                    page.wait_for_timeout(1500)
                    screenshot(page, f"intento_{intentos:02d}_home")

                    if not click_details_del_dia(page, intentos):
                        log.info(f"Reintentando en {INTERVALO_REINTENTO_SEG}s...")
                        time.sleep(INTERVALO_REINTENTO_SEG)
                        continue

                    reservado = seleccionar_y_reservar_cochera(page, intentos)
                except Exception as e:
                    log.warning(f"Error en intento #{intentos}: {e}")
                    screenshot(page, f"intento_{intentos:02d}_error")

                if reservado:
                    break

                log.info(f"Reintentando en {INTERVALO_REINTENTO_SEG}s...")
                time.sleep(INTERVALO_REINTENTO_SEG)

            if not reservado:
                log.error(f"❌ No se pudo reservar luego de {intentos} intentos.")
                screenshot(page, "error_reserva")
                sys.exit(1)

        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            try:
                screenshot(page, "error_reserva")
            except Exception:
                pass
            sys.exit(1)
        finally:
            browser.close()

    log.info("Script finalizado correctamente.")


if __name__ == "__main__":
    main()
