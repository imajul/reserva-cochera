"""
Observación de estados de cocheras en Parkalot.

Arranca a las 15:58 ARG, navega al mapa de mañana, espera las 16:00:00 exacto
y luego escanea TODAS las cocheras cada 500ms durante 2 minutos registrando
el color de cada una (negro=no disponible, verde=disponible, rojo=reservada/bloqueada).

El resultado se guarda en data/YYYY-MM-DD.json para acumular el patrón semanal.
"""

import os
import sys
import re
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── Reutilizar configuración del script principal ─────────────────────────────
PARKALOT_URL    = "https://app.parkalot.io/#/client"
EMAIL           = os.environ.get("PARKALOT_EMAIL", "")
PASSWORD        = os.environ.get("PARKALOT_PASSWORD", "")
TZ_ARG          = pytz.timezone("America/Argentina/Buenos_Aires")
HORA_APERTURA   = 16
MINUTO_APERTURA = 0

DURACION_SCAN_SEG  = 120   # 2 minutos de observación
INTERVALO_SCAN_SEG = 0.5   # scan cada 500ms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def ahora_arg() -> datetime:
    return datetime.now(TZ_ARG)


# ── Clasificación de color vía CSS computado ──────────────────────────────────

_COLOR_JS = """
(el) => {
    function parseRGB(s) {
        const m = (s || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
        return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : null;
    }
    function classifyRGB(rgb) {
        if (!rgb) return null;
        const [r, g, b] = rgb;
        if (r > 150 && r > g * 1.5 && r > b * 1.5) return 'rojo';
        if (g > 120 && g > r * 1.2 && g > b * 0.9) return 'verde';
        return null;
    }
    // Recolectar colores del elemento y sus hijos directos
    const signals = [];
    const collectColors = (node) => {
        const cs = window.getComputedStyle(node);
        signals.push(cs.backgroundColor, cs.borderLeftColor,
                     cs.color, cs.borderColor, cs.outlineColor);
    };
    collectColors(el);
    el.querySelectorAll('*').forEach(c => collectColors(c));

    for (const s of signals) {
        const c = classifyRGB(parseRGB(s));
        if (c === 'rojo' || c === 'verde') return c;
    }
    return 'negro';
}
"""


def _color_elemento(page, elemento) -> str:
    try:
        return page.evaluate(_COLOR_JS, elemento)
    except Exception:
        return "desconocido"


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page):
    log.info("Login en Parkalot...")
    page.goto(PARKALOT_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)
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
    log.info("Login OK ✓")


# ── Navegación al mapa de mañana ──────────────────────────────────────────────

def _ordinal_en(n: int) -> str:
    if 11 <= n % 100 <= 13:
        suffix = "TH"
    else:
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suffix}"


def navegar_al_mapa_manana(page) -> bool:
    """Navega al mapa de reservas de mañana. Retorna True si lo logró."""
    manana = (ahora_arg().date() + timedelta(days=1))
    manana_ordinal = _ordinal_en(manana.day).lower()

    log.info(f"Buscando mapa de mañana ({manana_ordinal} {manana.strftime('%B')})...")
    try:
        page.wait_for_selector("text=DETAILS", timeout=15000)
    except PlaywrightTimeoutError:
        log.warning("No hay botón DETAILS — reservas no habilitadas aún")
        return False

    for btn in page.get_by_text("DETAILS").all():
        try:
            ancestor = btn.locator(f"xpath=ancestor::*[contains(., '{manana_ordinal}')][1]")
            if ancestor.count() > 0:
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(500)
                log.info("Mapa de mañana abierto ✓")
                return True
        except Exception:
            continue

    log.warning(f"DETAILS de mañana ({manana_ordinal}) no encontrado")
    return False


# ── Scan de cocheras ──────────────────────────────────────────────────────────

def _scan_cocheras(page) -> dict:
    """Escanea todas las cocheras visibles y retorna {numero: color}."""
    resultado = {}
    try:
        # Scroll para asegurarse de ver todas (hasta que el conteo se estabilice)
        n_prev = -1
        for _ in range(12):
            items = page.locator("button.MuiButtonBase-root:has(h6)").all()
            for item in items:
                try:
                    box = item.bounding_box()
                    if not box or box["width"] < 150:
                        continue
                    num = int(item.locator("h6").inner_text(timeout=200).strip())
                    color = _color_elemento(page, item)
                    resultado[num] = color
                except Exception:
                    continue
            if len(resultado) == n_prev:
                break
            n_prev = len(resultado)
            if items:
                items[-1].scroll_into_view_if_needed()
                page.wait_for_timeout(80)
    except Exception as e:
        log.warning(f"Error en scan: {e}")
    return resultado


# ── Loop principal de observación ─────────────────────────────────────────────

def observar(page) -> list:
    """
    Espera las 16:00:00 exacto, luego escanea cada 500ms durante 2 minutos.
    Retorna lista de snapshots: [{timestamp, cocheras: {num: color}}, ...]
    """
    apertura_dt = ahora_arg().replace(
        hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
    )
    while ahora_arg() < apertura_dt:
        time.sleep(0.05)

    fin_dt = apertura_dt + timedelta(seconds=DURACION_SCAN_SEG)
    log.info(f"{'='*55}")
    log.info(f"  16:00:00 ARG — Iniciando observación de cocheras")
    log.info(f"  Escaneando cada {int(INTERVALO_SCAN_SEG*1000)}ms durante {DURACION_SCAN_SEG}s")
    log.info(f"{'='*55}")

    snapshots = []
    n_scan = 0

    while ahora_arg() <= fin_dt:
        t0 = time.monotonic()
        n_scan += 1
        ts = ahora_arg()
        cocheras = _scan_cocheras(page)

        snap = {
            "timestamp": ts.strftime("%H:%M:%S.%f")[:-3],
            "segundos_desde_apertura": round((ts - apertura_dt).total_seconds(), 2),
            "cocheras": {str(k): v for k, v in sorted(cocheras.items())}
        }
        snapshots.append(snap)

        # Log resumido cada 10 scans (~5s) o cuando cambia algo
        if n_scan == 1 or n_scan % 10 == 0:
            resumen = {c: v for c, v in cocheras.items()}
            verdes  = [k for k, v in resumen.items() if v == "verde"]
            rojos   = [k for k, v in resumen.items() if v == "rojo"]
            negros  = [k for k, v in resumen.items() if v == "negro"]
            log.info(
                f"[+{snap['segundos_desde_apertura']:.1f}s] "
                f"Scan #{n_scan} — "
                f"verde:{verdes} rojo:{rojos} negro:{negros}"
            )

        elapsed = time.monotonic() - t0
        sleep_time = max(0, INTERVALO_SCAN_SEG - elapsed)
        time.sleep(sleep_time)

    log.info(f"Observación finalizada. Total scans: {n_scan}")
    return snapshots


# ── Guardado de resultados ────────────────────────────────────────────────────

def guardar_resultados(snapshots: list):
    manana = (ahora_arg().date() + timedelta(days=1))
    fecha_str = manana.isoformat()
    dia_semana = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"][manana.weekday()]

    # Resumen: primer y último estado de cada cochera
    primer_snap = snapshots[0]["cocheras"] if snapshots else {}
    ultimo_snap = snapshots[-1]["cocheras"] if snapshots else {}

    # Determinar estado final de cada cochera
    todas_las_cocheras = set()
    for s in snapshots:
        todas_las_cocheras.update(int(k) for k in s["cocheras"])

    estado_final = {}
    for c in sorted(todas_las_cocheras):
        cs = str(c)
        # Buscar el primer momento en que apareció verde o rojo
        primer_verde = next(
            (s["segundos_desde_apertura"] for s in snapshots
             if s["cocheras"].get(cs) == "verde"), None
        )
        primer_rojo = next(
            (s["segundos_desde_apertura"] for s in snapshots
             if s["cocheras"].get(cs) == "rojo"), None
        )
        ultimo_color = ultimo_snap.get(cs, "desconocido")
        estado_final[cs] = {
            "ultimo_color": ultimo_color,
            "primer_verde_seg": primer_verde,
            "primer_rojo_seg": primer_rojo,
        }

    registro = {
        "fecha": fecha_str,
        "dia_semana": dia_semana,
        "hora_inicio_scan": snapshots[0]["timestamp"] if snapshots else None,
        "total_scans": len(snapshots),
        "cocheras": estado_final,
        "timeline": snapshots,
    }

    # Guardar observación diaria
    Path("data").mkdir(exist_ok=True)
    archivo_dia = Path(f"data/{fecha_str}.json")
    archivo_dia.write_text(json.dumps(registro, ensure_ascii=False, indent=2))
    log.info(f"Guardado: {archivo_dia}")

    # Actualizar resumen acumulado
    resumen_path = Path("data/resumen.json")
    if resumen_path.exists():
        resumen = json.loads(resumen_path.read_text())
    else:
        resumen = {}

    resumen[fecha_str] = {
        "dia_semana": dia_semana,
        "cocheras": {c: d["ultimo_color"] for c, d in estado_final.items()}
    }
    resumen_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2, sort_keys=True))
    log.info(f"Resumen acumulado actualizado: {resumen_path}")

    # Imprimir tabla de colores del día
    log.info(f"\n{'─'*50}")
    log.info(f"  RESUMEN: {fecha_str} ({dia_semana})")
    log.info(f"{'─'*50}")
    for c, d in estado_final.items():
        color = d["ultimo_color"]
        emoji = {"verde": "🟢", "rojo": "🔴", "negro": "⚫"}.get(color, "⬜")
        extra = ""
        if d["primer_verde_seg"] is not None:
            extra = f"  (verde a los {d['primer_verde_seg']:.1f}s)"
        elif d["primer_rojo_seg"] is not None:
            extra = f"  (rojo a los {d['primer_rojo_seg']:.1f}s)"
        log.info(f"  Cochera {c:>4}: {emoji} {color}{extra}")
    log.info(f"{'─'*50}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  Observación de cocheras — Parkalot")
    log.info(f"  {ahora_arg().strftime('%A %Y-%m-%d %H:%M:%S')} ARG")
    log.info("=" * 60)

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

            # Esperar hasta que el botón DETAILS de mañana esté disponible
            # (puede tardar si todavía no es las 16:00)
            ok = False
            while not ok:
                ok = navegar_al_mapa_manana(page)
                if not ok:
                    log.info("Mapa de mañana aún no disponible — reintentando en 5s...")
                    time.sleep(5)
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(500)

            snapshots = observar(page)
            guardar_resultados(snapshots)

        except Exception as e:
            log.exception(f"Error inesperado: {e}")
            sys.exit(1)
        finally:
            browser.close()

    log.info("Observación completada.")


if __name__ == "__main__":
    main()
