"""
Automatización de reserva de cochera en Parkalot.
Flujo:
  1. Arranca a las 15:55 ARG y espera hasta las 16:00
  2. Login
  3. Click en el SEGUNDO botón DETAILS (el del día siguiente)
  4. En el mapa, buscar cochera según orden de prioridad
  5. Click en la cochera → Click en RESERVE

Días de ejecución: domingo a jueves (para reservar lunes a viernes).
Orden de prioridad: 208 → 237 → 238 → primera disponible en la lista.
"""

import os
import sys
import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_URL    = "https://app.parkalot.io/#/client"
EMAIL           = os.environ.get("PARKALOT_EMAIL", "")
PASSWORD        = os.environ.get("PARKALOT_PASSWORD", "")

# Notificaciones WhatsApp vía CallMeBot (opcional)
WHATSAPP_PHONE  = os.environ.get("WHATSAPP_PHONE", "")   # Ej: 5491112345678
WHATSAPP_APIKEY = os.environ.get("WHATSAPP_APIKEY", "")

# Orden de prioridad de cocheras (209 eliminada — asignada por el admin)
COCHERAS_PRIORIDAD = [208, 237, 238]

# Días en que corre el script (para reservar el día siguiente hábil)
# Domingo=6, Lunes=0, Martes=1, Miércoles=2, Jueves=3
DIAS_EJECUCION  = {6, 0, 1, 2, 3}

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

def enviar_whatsapp(mensaje: str):
    if not WHATSAPP_PHONE or not WHATSAPP_APIKEY:
        log.info("WhatsApp no configurado — omitiendo notificación.")
        return
    try:
        texto = urllib.parse.quote(mensaje)
        url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={WHATSAPP_PHONE}&text={texto}&apikey={WHATSAPP_APIKEY}"
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            log.info(f"📲 WhatsApp enviado ✓ (status {resp.status})")
    except Exception as e:
        log.warning(f"No se pudo enviar WhatsApp: {e}")

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


def _ordinal_en(n: int) -> str:
    """1→'1ST', 2→'2ND', 3→'3RD', 14→'14TH', etc."""
    if 11 <= n % 100 <= 13:
        suffix = "TH"
    else:
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suffix}"


def _corregir_fecha_si_necesario(page, prefix: str):
    """
    Verifica que la página de reserva muestre mañana.
    Si muestra hoy, intenta corregirlo:
      1) Reemplazando la fecha en la URL (si la URL la contiene)
      2) Clickeando el botón de navegación siguiente ( > )
    """
    hoy   = ahora_arg().date()
    manana = hoy + timedelta(days=1)
    hoy_iso    = hoy.isoformat()     # "2026-05-14"
    manana_iso = manana.isoformat()  # "2026-05-15"

    # ── Estrategia 1: URL contiene la fecha ──────────────────────────────
    url = page.url
    if manana_iso in url:
        log.info(f"Fecha correcta en URL: {manana_iso} ✓")
        return
    if hoy_iso in url:
        nueva_url = url.replace(hoy_iso, manana_iso)
        log.info(f"URL muestra hoy — navegando a {manana_iso}...")
        page.goto(nueva_url, wait_until="domcontentloaded")
        page.wait_for_timeout(300)
        screenshot(page, f"{prefix}_fecha_corregida")
        log.info("Fecha corregida por URL ✓")
        return

    # ── Estrategia 2: detectar fecha en heading y click en botón siguiente ─
    hoy_mes     = hoy.strftime("%B").upper()       # "MAY"
    hoy_ordinal = _ordinal_en(hoy.day)             # "14TH"

    try:
        textos = page.locator(
            "h1, h2, h3, h4, h5, h6, "
            "[class*='title' i], [class*='header' i], [class*='date' i], "
            "[class*='Typography']"
        ).all_inner_texts()

        muestra_hoy = any(
            hoy_ordinal in t.upper() and hoy_mes in t.upper()
            for t in textos
        )

        if not muestra_hoy:
            log.info("Fecha en página parece correcta ✓")
            return

        log.info(f"Página muestra hoy ({hoy_ordinal} {hoy_mes}) — avanzando al día siguiente...")
        selectores_next = [
            "[data-testid='ChevronRightIcon']",
            "[data-testid='NavigateNextIcon']",
            "[data-testid='ArrowForwardIcon']",
            "button[aria-label*='next' i]",
            "button[aria-label*='siguiente' i]",
            "button[aria-label*='forward' i]",
        ]
        for sel in selectores_next:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=500):
                    btn.click()
                    page.wait_for_timeout(300)
                    screenshot(page, f"{prefix}_fecha_corregida")
                    log.info("Fecha avanzada al día siguiente ✓")
                    return
            except Exception:
                continue

        log.warning("No se pudo avanzar al día siguiente — continuando igual.")
    except Exception as e:
        log.warning(f"No se pudo verificar fecha en página: {e}")


def click_details_del_dia(page, intento: int = 0) -> bool:
    """
    Hace click en el SEGUNDO botón DETAILS (el del día siguiente).
    Cuando hay dos tarjetas visibles, la primera es el día de hoy
    y la segunda es el día siguiente.
    """
    prefix = f"intento_{intento:02d}"
    log.info("Buscando botones DETAILS...")
    page.wait_for_timeout(300)
    try:
        page.wait_for_selector("text=DETAILS", timeout=8000)
        details_btns = page.get_by_text("DETAILS").all()
        log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
        screenshot(page, f"{prefix}_details_encontrado")
        # Siempre clickear el último (el del día siguiente)
        details_btns[-1].click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        screenshot(page, f"{prefix}_post_details")
        log.info("Click en DETAILS ✓")

        # Verificar que la página muestre mañana y no hoy
        _corregir_fecha_si_necesario(page, prefix)
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
    Itera las cocheras en orden de prioridad y reserva la primera disponible.
    Si el botón RESERVE está deshabilitado (cochera ya reservada), pasa a la siguiente
    inmediatamente sin esperar ningún timeout.
    """
    prefix = f"intento_{intento:02d}"
    log.info("Obteniendo cocheras disponibles en la lista...")
    page.wait_for_timeout(300)
    screenshot(page, f"{prefix}_mapa")

    cocheras_disponibles = {}
    try:
        # Filtramos por ancho: los ítems de la lista lateral son anchos (>150px)
        # mientras que los marcadores del mapa son pequeños (~30-50px).
        # Esto evita clickear marcadores del mapa en lugar de ítems de la lista.
        todos = page.locator("button.MuiButtonBase-root:has(h6)").all()
        for item in todos:
            try:
                box = item.bounding_box()
                if box is None or box["width"] < 150:
                    continue  # marcador del mapa, ignorar
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

    log.info(f"Cocheras en lista: {sorted(cocheras_disponibles.keys())}")

    # Orden: primero las prioritarias, luego el resto ordenadas
    cocheras_a_intentar = [c for c in COCHERAS_PRIORIDAD if c in cocheras_disponibles]
    for c in sorted(cocheras_disponibles.keys()):
        if c not in cocheras_a_intentar:
            cocheras_a_intentar.append(c)
    log.info(f"Orden de intentos: {cocheras_a_intentar}")

    for cochera_num in cocheras_a_intentar:
        elemento = cocheras_disponibles[cochera_num]
        log.info(f"Seleccionando cochera {cochera_num}...")

        elemento.scroll_into_view_if_needed()
        elemento.click()
        page.wait_for_timeout(200)
        screenshot(page, f"{prefix}_cochera_{cochera_num}_sel")

        # Verificar si el botón RESERVE existe y está habilitado
        reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
        try:
            reserve_btn.wait_for(timeout=3000)
        except PlaywrightTimeoutError:
            log.warning(f"Cochera {cochera_num}: botón RESERVE no encontrado. Siguiente...")
            screenshot(page, f"{prefix}_cochera_{cochera_num}_sin_reserve")
            continue

        if not reserve_btn.is_enabled():
            # Estado de transición (gris): esperar y reintentar antes de descartar
            page.wait_for_timeout(600)
            if not reserve_btn.is_enabled():
                log.warning(f"Cochera {cochera_num}: ya reservada (RESERVE deshabilitado). Siguiente...")
                screenshot(page, f"{prefix}_cochera_{cochera_num}_ocupada")
                continue

        # Cochera disponible — reservar
        log.info(f"Cochera {cochera_num} disponible — reservando...")
        screenshot(page, f"{prefix}_pre_reserve_{cochera_num}")
        reserve_btn.click()
        log.info("Click en RESERVE ✓")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(3000)
        screenshot(page, f"{prefix}_post_reserve_{cochera_num}")

        # Confirmar popup si aparece
        try:
            confirm = page.locator(
                "button:has-text('Confirm'), button:has-text('OK'), "
                "button:has-text('Yes'), button:has-text('Aceptar')"
            ).first
            confirm.wait_for(timeout=3000)
            confirm.click()
            page.wait_for_timeout(1500)
            screenshot(page, f"{prefix}_confirmacion_{cochera_num}")
            log.info("Confirmación adicional aceptada ✓")
        except PlaywrightTimeoutError:
            pass

        screenshot(page, "resultado_reserva")
        log.info(f"✅ Reserva exitosa — Cochera {cochera_num}")
        enviar_whatsapp(
            f"✅ Cochera {cochera_num} reservada para el {fecha_manana_str()} 🚗"
        )
        return True

    log.warning("Se intentaron todas las cocheras disponibles — todas ocupadas.")
    screenshot(page, f"{prefix}_todas_ocupadas")
    return False


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

            # Pre-posicionarse en el mapa antes de las 16:00
            en_mapa = False
            url_mapa = None
            log.info("Intentando pre-cargar el mapa de cocheras...")
            try:
                if click_details_del_dia(page, 0):
                    en_mapa = True
                    url_mapa = page.url
                    log.info(f"Pre-posicionado en el mapa ✓")
                else:
                    log.info("Mapa aún no disponible — se cargará en el loop principal.")
            except Exception:
                pass

            limite = ahora_arg() + timedelta(minutes=TIMEOUT_ESPERA_MIN)
            reservado = False
            intentos = 0

            while ahora_arg() <= limite:
                intentos += 1
                log.info(f"[Intento #{intentos} — {ahora_arg().strftime('%H:%M:%S')} ARG]")

                try:
                    if en_mapa and url_mapa:
                        log.info("Recargando mapa de cocheras...")
                        page.goto(url_mapa, wait_until="domcontentloaded")
                        page.wait_for_timeout(300)
                        screenshot(page, f"intento_{intentos:02d}_reload")
                    else:
                        page.goto(PARKALOT_URL, wait_until="networkidle")
                        page.wait_for_timeout(300)
                        screenshot(page, f"intento_{intentos:02d}_home")

                        if not click_details_del_dia(page, intentos):
                            log.info(f"Reintentando en {INTERVALO_REINTENTO_SEG}s...")
                            time.sleep(INTERVALO_REINTENTO_SEG)
                            continue

                        en_mapa = True
                        url_mapa = page.url

                    reservado = seleccionar_y_reservar_cochera(page, intentos)
                except Exception as e:
                    log.warning(f"Error en intento #{intentos}: {e}")
                    screenshot(page, f"intento_{intentos:02d}_error")
                    en_mapa = False
                    url_mapa = None

                if reservado:
                    break

                ahora_actual = ahora_arg()
                apertura = ahora_actual.replace(
                    hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
                )
                intervalo = 1 if ahora_actual >= apertura else INTERVALO_REINTENTO_SEG
                log.info(f"Reintentando en {intervalo}s...")
                time.sleep(intervalo)

            if not reservado:
                log.error(f"❌ No se pudo reservar luego de {intentos} intentos.")
                screenshot(page, "error_reserva")
                enviar_whatsapp(
                    f"❌ No se pudo reservar cochera para el {fecha_manana_str()}. "
                    f"Revisá el log en GitHub Actions."
                )
                sys.exit(1)

        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            try:
                screenshot(page, "error_reserva")
            except Exception:
                pass
            enviar_whatsapp(
                f"❌ Error inesperado al reservar cochera para el {fecha_manana_str()}. "
                f"Revisá el log en GitHub Actions."
            )
            sys.exit(1)
        finally:
            browser.close()

    log.info("Script finalizado correctamente.")


if __name__ == "__main__":
    main()
