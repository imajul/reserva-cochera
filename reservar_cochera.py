"""
Automatización de reserva de cochera en Parkalot.
Flujo:
  1. Arranca a las 15:55 ARG y espera hasta las 16:00
  2. Login
  3. Click en el SEGUNDO botón DETAILS (el del día siguiente)
  4. En el mapa, buscar cochera según orden de prioridad
  5. Click en la cochera → Click en RESERVE

Días de ejecución: domingo a jueves (para reservar lunes a viernes).
Orden de prioridad: 209 → 208 → 237 → primera disponible en la lista.
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

# Orden de prioridad de cocheras
COCHERAS_PRIORIDAD = [209, 208, 237]

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
        log.info(f"Son las {ahora.strftime('%H:%M:%S')} ARG. Esperando hasta las {pre_apertura.strftime('%H:%M:%S')} ({int(espera_seg)}s)...")
        time.sleep(espera_seg)
    log.info("Entrando en modo de espera activa...")

_screenshot_counter = 0

def screenshot(page, nombre: str):
    global _screenshot_counter
    _screenshot_counter += 1
    ts = ahora_arg().strftime("%H%M%S")
    path = f"{_screenshot_counter:03d}_{nombre}_{ts}.png"
    try:
        page.screenshot(path=path, full_page=True)
        log.info(f"📸 Screenshot: {path}")
    except Exception as e:
        log.warning(f"No se pudo guardar screenshot {path}: {e}")


LOGIN_REINTENTOS   = 3
LOGIN_PAUSA_SEG    = 5

def login(page):
    log.info("Navegando a Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "01_login_form")

    for intento in range(1, LOGIN_REINTENTOS + 1):
        if intento > 1:
            log.info(f"Reintentando login (intento {intento}/{LOGIN_REINTENTOS})...")
            page.goto(PARKALOT_URL, wait_until="networkidle")
            page.wait_for_timeout(1000)

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
        screenshot(page, f"0{intento + 1}_post_login")

        # Verificar que el login fue exitoso: el formulario debe desaparecer
        email_locator = page.locator(
            "input[type='email'], input[name='email'], "
            "input[placeholder*='mail' i], input[formcontrolname='email']"
        ).first
        try:
            email_locator.wait_for(state="hidden", timeout=3000)
            log.info("Sesión iniciada ✓")
            return
        except PlaywrightTimeoutError:
            # El formulario sigue visible — puede ser error transitorio del servidor
            error_texto = ""
            try:
                error_texto = page.locator(
                    "[class*='error' i], [class*='alert' i], [role='alert']"
                ).first.inner_text(timeout=1000).strip()
            except Exception:
                pass
            log.warning(
                f"Login intento {intento}/{LOGIN_REINTENTOS} falló"
                + (f": {error_texto}" if error_texto else " (formulario sigue visible)")
            )
            screenshot(page, f"0{intento + 1}_login_error")
            if intento < LOGIN_REINTENTOS:
                log.info(f"Esperando {LOGIN_PAUSA_SEG}s antes de reintentar...")
                time.sleep(LOGIN_PAUSA_SEG)

    raise RuntimeError(
        f"Login falló tras {LOGIN_REINTENTOS} intentos. "
        "Verificar credenciales o estado de Parkalot."
    )


def _ordinal_en(n: int) -> str:
    if 11 <= n % 100 <= 13:
        suffix = "TH"
    else:
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suffix}"


def _corregir_fecha_si_necesario(page, prefix: str):
    """Garantiza que la página muestra el mapa de MAÑANA, nunca el de hoy.

    El script siempre reserva para el día siguiente. Si el usuario liberó su
    cochera hoy, Parkalot puede mostrar un DETAILS para hoy que, de clickearse,
    llevaría al mapa de hoy. Esta función detecta y corrige ese caso.
    """
    hoy    = ahora_arg().date()
    manana = hoy + timedelta(days=1)
    hoy_iso    = hoy.isoformat()
    manana_iso = manana.isoformat()

    # ── 1. Verificación por URL (más confiable) ───────────────────────────────
    url = page.url
    if manana_iso in url:
        log.info(f"Fecha correcta en URL: {manana_iso} ✓")
        return
    if hoy_iso in url:
        nueva_url = url.replace(hoy_iso, manana_iso)
        log.info(f"URL muestra hoy ({hoy_iso}) — corrigiendo a {manana_iso}...")
        page.goto(nueva_url, wait_until="domcontentloaded")
        page.wait_for_timeout(300)
        screenshot(page, f"{prefix}_fecha_corregida_url")
        log.info("Fecha corregida por URL ✓")
        return

    # ── 2. Verificación por texto de la página ────────────────────────────────
    hoy_ordinal    = _ordinal_en(hoy.day)
    manana_ordinal = _ordinal_en(manana.day)
    hoy_mes        = hoy.strftime("%B").upper()
    manana_mes     = manana.strftime("%B").upper()

    try:
        textos = page.locator(
            "h1, h2, h3, h4, h5, h6, "
            "[class*='title' i], [class*='header' i], [class*='date' i], "
            "[class*='Typography']"
        ).all_inner_texts()
        textos_upper = [t.upper() for t in textos]

        muestra_manana = any(
            manana_ordinal in t and manana_mes in t for t in textos_upper
        )
        muestra_hoy = any(
            hoy_ordinal in t and hoy_mes in t for t in textos_upper
        )

        if muestra_manana:
            log.info(f"Fecha correcta en página: {manana_ordinal} {manana_mes} ✓")
            return

        selectores_next = [
            "[data-testid='ChevronRightIcon']",
            "[data-testid='NavigateNextIcon']",
            "[data-testid='ArrowForwardIcon']",
            "button[aria-label*='next' i]",
            "button[aria-label*='siguiente' i]",
            "button[aria-label*='forward' i]",
        ]

        if muestra_hoy:
            log.warning(
                f"Página muestra HOY ({hoy_ordinal} {hoy_mes}) en lugar de mañana "
                f"({manana_ordinal} {manana_mes}) — avanzando..."
            )
        else:
            # No se detectó ninguna fecha conocida; avanzar igual por precaución.
            log.warning(
                f"No se pudo confirmar fecha en página. "
                f"Esperado: {manana_ordinal} {manana_mes}. Intentando avanzar al día siguiente..."
            )

        screenshot(page, f"{prefix}_fecha_incorrecta")
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

        log.warning("No se encontró botón 'siguiente' — la fecha puede ser incorrecta.")
    except Exception as e:
        log.warning(f"No se pudo verificar fecha en página: {e}")


def click_details_del_dia(page, intento: int = 0) -> bool:
    prefix = f"intento_{intento:02d}"
    log.info("Buscando botones DETAILS...")
    page.wait_for_timeout(300)
    try:
        page.wait_for_selector("text=DETAILS", timeout=8000)
        details_btns = page.get_by_text("DETAILS").all()
        log.info(f"Botones DETAILS encontrados: {len(details_btns)}")
        screenshot(page, f"{prefix}_details_encontrado")
        details_btns[-1].click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        screenshot(page, f"{prefix}_post_details")
        log.info("Click en DETAILS ✓")
        _corregir_fecha_si_necesario(page, prefix)
        return True
    except PlaywrightTimeoutError:
        log.warning("No se encontró el botón DETAILS — las reservas aún no están habilitadas.")
        screenshot(page, f"{prefix}_sin_details")
        return False


def seleccionar_y_reservar_cochera(page, intento: int = 0) -> bool:
    prefix = f"intento_{intento:02d}"
    log.info("Obteniendo cocheras disponibles en la lista...")
    page.wait_for_timeout(300)
    screenshot(page, f"{prefix}_mapa")

    cocheras_disponibles = {}
    try:
        n_previo = -1
        for scroll_iter in range(10):
            todos = page.locator("button.MuiButtonBase-root:has(h6)").all()
            items_esta_iter = {}
            for item in todos:
                try:
                    box = item.bounding_box()
                    if box and box["width"] >= 150:
                        n = int(item.locator("h6").inner_text().strip())
                        items_esta_iter[n] = item
                except (ValueError, Exception):
                    continue

            cocheras_disponibles.update(items_esta_iter)
            log.info(f"  scroll iter {scroll_iter}: {len(items_esta_iter)} ítems en viewport → acumulado {sorted(cocheras_disponibles.keys())}")
            screenshot(page, f"{prefix}_scroll_{scroll_iter:02d}")

            if len(cocheras_disponibles) == n_previo:
                break
            n_previo = len(cocheras_disponibles)

            if all(p in cocheras_disponibles for p in COCHERAS_PRIORIDAD):
                log.info("Cocheras prioritarias localizadas — deteniendo scroll")
                break

            if items_esta_iter:
                list(items_esta_iter.values())[-1].scroll_into_view_if_needed()
                page.wait_for_timeout(200)

    except Exception as e:
        log.error(f"Error obteniendo lista de cocheras: {e}")
        screenshot(page, f"{prefix}_error_lista")
        return False

    if not cocheras_disponibles:
        log.warning("No hay cocheras disponibles en la lista.")
        screenshot(page, f"{prefix}_sin_cocheras")
        return False

    log.info(f"Cocheras en lista: {sorted(cocheras_disponibles.keys())}")

    cocheras_a_intentar = [c for c in COCHERAS_PRIORIDAD if c in cocheras_disponibles]
    for c in sorted(cocheras_disponibles.keys()):
        if c not in cocheras_a_intentar:
            cocheras_a_intentar.append(c)
    log.info(f"Orden de intentos: {cocheras_a_intentar}")

    def _reubicar_cochera(num: int):
        """Busca cochera por número en el DOM actual (con scroll si hace falta)."""
        for scroll_iter in range(10):
            items = page.locator("button.MuiButtonBase-root:has(h6)").all()
            for item in items:
                try:
                    box = item.bounding_box()
                    if box and box["width"] >= 150 and int(item.locator("h6").inner_text().strip()) == num:
                        return item
                except Exception:
                    continue
            if not items:
                break
            items[-1].scroll_into_view_if_needed()
            page.wait_for_timeout(200)
        return None

    for cochera_num in cocheras_a_intentar:
        elemento = cocheras_disponibles[cochera_num]
        log.info(f"Seleccionando cochera {cochera_num}...")

        try:
            num_en_dom = int(elemento.locator("h6").inner_text(timeout=500).strip())
        except Exception:
            log.warning(f"Cochera {cochera_num}: referencia inválida — saltando")
            continue

        if num_en_dom != cochera_num:
            log.warning(f"Cochera {cochera_num}: nodo reciclado (DOM muestra {num_en_dom}) — reubicando...")
            elemento = None
            for item in page.locator("button.MuiButtonBase-root:has(h6)").all():
                try:
                    box = item.bounding_box()
                    if box and box["width"] >= 150 and int(item.locator("h6").inner_text().strip()) == cochera_num:
                        elemento = item
                        break
                except Exception:
                    continue
            if elemento is None:
                log.warning(f"Cochera {cochera_num}: no hallada tras reciclaje — saltando")
                continue

        try:
            elemento.scroll_into_view_if_needed()
            elemento.click()
        except Exception:
            log.warning(f"Cochera {cochera_num}: elemento fuera del DOM (scroll virtual) — saltando")
            continue
        page.wait_for_timeout(200)
        screenshot(page, f"{prefix}_cochera_{cochera_num}_sel")

        reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
        try:
            reserve_btn.wait_for(timeout=3000)
        except PlaywrightTimeoutError:
            log.warning(f"Cochera {cochera_num}: botón RESERVE no encontrado. Siguiente...")
            screenshot(page, f"{prefix}_cochera_{cochera_num}_sin_reserve")
            continue

        if not reserve_btn.is_enabled():
            # Parkalot puede mostrar el botón deshabilitado transitoriamente al abrirse
            # la ventana de reservas. Un refresh rápido fuerza el estado real sin esperar.
            log.info(f"Cochera {cochera_num}: RESERVE deshabilitado — intentando refresh rápido...")
            screenshot(page, f"{prefix}_cochera_{cochera_num}_disabled_pre_refresh")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            screenshot(page, f"{prefix}_cochera_{cochera_num}_post_reload")

            elemento_post = _reubicar_cochera(cochera_num)
            if elemento_post is None:
                log.warning(f"Cochera {cochera_num}: no hallada tras refresh — saltando")
                screenshot(page, f"{prefix}_cochera_{cochera_num}_no_hallada_post_refresh")
                continue

            try:
                elemento_post.scroll_into_view_if_needed()
                elemento_post.click()
            except Exception:
                log.warning(f"Cochera {cochera_num}: click falló tras refresh — saltando")
                continue
            page.wait_for_timeout(300)
            screenshot(page, f"{prefix}_cochera_{cochera_num}_sel_post_refresh")

            reserve_btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
            try:
                reserve_btn.wait_for(timeout=3000)
            except PlaywrightTimeoutError:
                log.warning(f"Cochera {cochera_num}: botón RESERVE no encontrado tras refresh — saltando")
                screenshot(page, f"{prefix}_cochera_{cochera_num}_sin_reserve_post_refresh")
                continue

            if not reserve_btn.is_enabled():
                log.warning(f"Cochera {cochera_num}: RESERVE sigue deshabilitado tras refresh — ya reservada. Siguiente...")
                screenshot(page, f"{prefix}_cochera_{cochera_num}_ocupada")
                continue

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
            # Login temprano (~15:56) antes de que el backend de Parkalot
            # se sature con el pico de usuarios a las 16:00.
            login(page)

            # ── Pre-armado ──────────────────────────────────────────────────
            # Navegar al mapa y pre-seleccionar la cochera prioritaria ANTES
            # de esperar las 16:00. Al abrirse el sistema, el único paso
            # pendiente es un click en RESERVE — sin navegación ni scroll.
            pre_armed = False
            cochera_prearmada = None
            reserve_btn_prearmado = None
            url_mapa = None

            log.info("Intentando pre-armar cochera prioritaria en el mapa...")
            try:
                if click_details_del_dia(page, 0):
                    url_mapa = page.url
                    screenshot(page, "pre_arm_mapa")
                    for cochera_num in COCHERAS_PRIORIDAD:
                        elemento = None
                        for scroll_iter in range(8):
                            items = page.locator("button.MuiButtonBase-root:has(h6)").all()
                            for item in items:
                                try:
                                    box = item.bounding_box()
                                    if box and box["width"] >= 150 and int(item.locator("h6").inner_text().strip()) == cochera_num:
                                        elemento = item
                                        break
                                except Exception:
                                    continue
                            if elemento:
                                break
                            if items:
                                items[-1].scroll_into_view_if_needed()
                                page.wait_for_timeout(150)
                        if elemento is None:
                            log.info(f"Pre-armado: cochera {cochera_num} no encontrada en lista")
                            continue
                        try:
                            elemento.scroll_into_view_if_needed()
                            elemento.click()
                            page.wait_for_timeout(300)
                            btn = page.locator("button.MuiLoadingButton-root:has-text('Reserve')").first
                            btn.wait_for(timeout=2000)
                            reserve_btn_prearmado = btn
                            cochera_prearmada = cochera_num
                            pre_armed = True
                            log.info(f"Pre-armado: cochera {cochera_num} seleccionada, RESERVE visible ✓")
                            screenshot(page, f"pre_arm_cochera_{cochera_num}")
                            break
                        except Exception as e:
                            log.warning(f"Pre-armado: cochera {cochera_num} — {e}")
                else:
                    log.info("Mapa no disponible aún — se intentará en el loop principal.")
            except Exception as e:
                log.warning(f"Pre-armado falló: {e}")

            # ── Esperar hasta 15:59:55 ───────────────────────────────────────
            esperar_hasta_previa_apertura()

            reservado = False
            intentos = 0

            # ── Fase rápida: polling pre-armado ─────────────────────────────
            # Si la cochera ya está seleccionada, sólo esperamos que RESERVE
            # se habilite y clickeamos. Sin navegación ni scroll en el momento
            # crítico. Polling cada 100ms durante hasta 25 segundos.
            if pre_armed and reserve_btn_prearmado is not None:
                apertura_dt = ahora_arg().replace(
                    hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
                )
                while ahora_arg() < apertura_dt:
                    time.sleep(0.05)

                log.info(
                    f"16:00:00 ARG — polling RESERVE cochera {cochera_prearmada} "
                    f"({ahora_arg().strftime('%H:%M:%S.%f')})"
                )
                screenshot(page, f"pre_arm_inicio_polling_{cochera_prearmada}")

                try:
                    for _ in range(250):  # hasta 25s a 100ms
                        try:
                            if reserve_btn_prearmado.is_enabled():
                                ts = ahora_arg().strftime('%H:%M:%S.%f')
                                log.info(f"RESERVE habilitado a las {ts} ✓")
                                screenshot(page, f"pre_arm_reserve_ok_{cochera_prearmada}")
                                reserve_btn_prearmado.click()
                                log.info("Click en RESERVE ✓ (pre-armado)")
                                page.wait_for_timeout(3000)
                                screenshot(page, f"pre_arm_post_reserve_{cochera_prearmada}")
                                try:
                                    confirm = page.locator(
                                        "button:has-text('Confirm'), button:has-text('OK'), "
                                        "button:has-text('Yes'), button:has-text('Aceptar')"
                                    ).first
                                    confirm.wait_for(timeout=3000)
                                    confirm.click()
                                    page.wait_for_timeout(1500)
                                    screenshot(page, f"pre_arm_confirmacion_{cochera_prearmada}")
                                    log.info("Confirmación aceptada ✓")
                                except PlaywrightTimeoutError:
                                    pass
                                screenshot(page, "resultado_reserva")
                                log.info(f"✅ Reserva exitosa — Cochera {cochera_prearmada}")
                                enviar_whatsapp(
                                    f"✅ Cochera {cochera_prearmada} reservada para el {fecha_manana_str()} 🚗"
                                )
                                reservado = True
                                break
                        except Exception as e:
                            log.warning(f"Error en polling pre-armado: {e}")
                            break
                        time.sleep(0.1)

                    if not reservado:
                        log.warning(
                            f"Pre-armado: RESERVE no se habilitó en 25s para cochera "
                            f"{cochera_prearmada} — continuando con loop general."
                        )
                        screenshot(page, "pre_arm_timeout")
                except Exception as e:
                    log.warning(f"Fase pre-armada falló inesperadamente: {e}")

            # ── Loop general (fallback o primer intento si no hubo pre-armado) ─
            en_mapa = url_mapa is not None
            limite = ahora_arg() + timedelta(minutes=TIMEOUT_ESPERA_MIN)

            while not reservado and ahora_arg() <= limite:
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
