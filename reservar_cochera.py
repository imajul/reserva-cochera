"""
Automatización de reserva de cochera en Parkalot.
- Arranca a las 15:55 ARG y espera activamente hasta que se habilite la reserva a las 16:00.
- Reserva la cochera 237 (o la más cercana disponible si está ocupada).
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
TARGET_SPOT     = 237
DIAS_RESERVA    = {0, 1, 2, 4}   # Lunes=0, Martes=1, Miércoles=2, Viernes=4
TZ_ARG          = pytz.timezone("America/Argentina/Buenos_Aires")

# Hora en que Parkalot habilita las reservas
HORA_APERTURA   = 16
MINUTO_APERTURA = 0

# Segundos entre cada reintento en el loop de espera activa
INTERVALO_REINTENTO_SEG = 5

# Máximo tiempo esperando después de las 16:00 antes de rendirse (minutos)
TIMEOUT_ESPERA_MIN = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


# ─── Utilidades ───────────────────────────────────────────────────────────────

def ahora_arg() -> datetime:
    return datetime.now(TZ_ARG)


def dia_siguiente_es_habil() -> bool:
    manana_weekday = (date.today().weekday() + 1) % 7
    return manana_weekday in DIAS_RESERVA


def fecha_manana_str() -> str:
    manana = date.today() + timedelta(days=1)
    return manana.strftime("%Y-%m-%d")


def esperar_hasta_previa_apertura():
    """
    Duerme hasta 10 segundos antes de las 16:00 ARG.
    El loop de intentos cubre el último tramo con precisión de segundos.
    """
    ahora = ahora_arg()
    apertura = ahora.replace(
        hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
    )
    pre_apertura = apertura - timedelta(seconds=10)

    if ahora < pre_apertura:
        espera_seg = (pre_apertura - ahora).total_seconds()
        log.info(
            f"Son las {ahora.strftime('%H:%M:%S')} ARG. "
            f"Esperando hasta las 15:59:50 ({int(espera_seg)} segundos)..."
        )
        time.sleep(espera_seg)

    log.info("Entrando en modo de espera activa — verificando cada 5s hasta que se habilite...")


def encontrar_cochera_mas_cercana(spots: list[int]) -> int | None:
    if not spots:
        return None
    return min(spots, key=lambda x: abs(x - TARGET_SPOT))


def reserva_habilitada(page) -> bool:
    """
    Retorna True si detecta cocheras disponibles para seleccionar.
    """
    try:
        # Verificar que no haya mensaje de "no disponible"
        bloqueado = page.locator(
            "text='no disponible', text='no habilitado', text='fuera de horario', "
            "text='not available', .locked, .not-available"
        ).first.is_visible(timeout=800)
        if bloqueado:
            return False

        cocheras = page.locator(
            ".spot:not(.disabled):not(.occupied), "
            ".parking-spot:not(.disabled):not(.occupied), "
            "[data-spot]:not([disabled]), [data-number]:not([disabled])"
        ).count()
        return cocheras > 0
    except Exception:
        return False


# ─── Flujo de reserva ─────────────────────────────────────────────────────────

def login(page):
    log.info("Navegando a Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)

    log.info("Iniciando sesión...")
    page.locator(
        "input[type='email'], input[name='email'], input[placeholder*='mail' i]"
    ).first.fill(EMAIL)
    page.locator("input[type='password']").first.fill(PASSWORD)
    page.locator(
        "button[type='submit'], button:has-text('Ingresar'), button:has-text('Login')"
    ).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    log.info("Sesión iniciada ✓")


def seleccionar_fecha(page, fecha_str: str):
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

    page.wait_for_timeout(1000)


def intentar_reservar(page, fecha_str: str) -> bool:
    """
    Recarga, navega a la fecha y trata de reservar.
    Retorna True si la reserva fue exitosa.
    """
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1200)
    seleccionar_fecha(page, fecha_str)

    if not reserva_habilitada(page):
        return False

    log.info("¡Reservas habilitadas! Buscando cochera 237...")

    # ── Intentar cochera target ────────────────────────────────────────────
    cochera_seleccionada = None
    for selector in [
        f"[data-spot='{TARGET_SPOT}']",
        f"[data-number='{TARGET_SPOT}']",
        f".spot:has-text('{TARGET_SPOT}')",
        f"text='{TARGET_SPOT}'",
    ]:
        try:
            el = page.locator(selector).first
            if not el.is_visible(timeout=1200):
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

    # ── Fallback: cochera más cercana ──────────────────────────────────────
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
            log.warning("Sin cocheras disponibles.")
            return False

        mejor = encontrar_cochera_mas_cercana([n for n, _ in disponibles])
        for n, el in disponibles:
            if n == mejor:
                log.info(f"Seleccionando cochera alternativa: {mejor}")
                el.click()
                cochera_seleccionada = mejor
                break

    if cochera_seleccionada is None:
        return False

    page.wait_for_timeout(800)

    # ── Confirmar ─────────────────────────────────────────────────────────
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
        return False

    # ── Verificar éxito ───────────────────────────────────────────────────
    try:
        page.locator(
            "text='confirmad', text='exitosa', text='success', text='reservad'"
        ).first.wait_for(timeout=5000)
    except PlaywrightTimeoutError:
        pass  # Puede no haber mensaje explícito

    log.info(f"✅ Reserva exitosa — Cochera {cochera_seleccionada} para el {fecha_str}")
    page.screenshot(path="resultado_reserva.png")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

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

    fecha_str = fecha_manana_str()
    log.info(f"Objetivo: reservar cochera {TARGET_SPOT} para el {fecha_str}")

    # Dormir hasta 10 segundos antes de las 16:00
    esperar_hasta_previa_apertura()

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

            apertura_arg = ahora_arg().replace(
                hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
            )
            limite = apertura_arg + timedelta(minutes=TIMEOUT_ESPERA_MIN)

            reservado = False
            intentos  = 0

            while ahora_arg() <= limite:
                intentos += 1
                log.info(
                    f"[Intento #{intentos} — {ahora_arg().strftime('%H:%M:%S')} ARG] "
                    "Verificando disponibilidad..."
                )
                try:
                    reservado = intentar_reservar(page, fecha_str)
                except Exception as e:
                    log.warning(f"Error en intento #{intentos}: {e}")

                if reservado:
                    break

                log.info(f"No disponible aún. Reintentando en {INTERVALO_REINTENTO_SEG}s...")
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
