"""
Automatización de reserva de cochera en Parkalot.
Flujo:
  1. Arranca a las 15:55 ARG y espera hasta las 16:00
  2. Renueva el Firebase ID Token via securetoken.googleapis.com
  3. Llama directamente a la Cloud Function de Parkalot para reservar
  4. Intenta cocheras en orden de prioridad: 209 → 208 → 237

Días de ejecución: domingo a jueves (para reservar lunes a viernes).
"""

import os
import sys
import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pytz
import httpx

# ─── Configuración ────────────────────────────────────────────────────────────
PARKALOT_REFRESH_TOKEN = os.environ.get("PARKALOT_REFRESH_TOKEN", "")
PARKALOT_UID           = os.environ.get("PARKALOT_UID", "")
PARKALOT_API_KEY       = os.environ.get("PARKALOT_API_KEY", "")

# Notificaciones WhatsApp vía CallMeBot (opcional)
WHATSAPP_PHONE  = os.environ.get("WHATSAPP_PHONE", "")
WHATSAPP_APIKEY = os.environ.get("WHATSAPP_APIKEY", "")

# Orden de prioridad de cocheras
COCHERAS_PRIORIDAD = [209, 208, 237]

# Días en que corre el script (para reservar el día siguiente hábil)
# Domingo=6, Lunes=0, Martes=1, Miércoles=2, Jueves=3
DIAS_EJECUCION = {6, 0, 1, 2, 3}

TZ_ARG          = pytz.timezone("America/Argentina/Buenos_Aires")
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
INTERVALO_REINTENTO_SEG = 5
TIMEOUT_ESPERA_MIN = 10

FIREBASE_TOKEN_URL   = "https://securetoken.googleapis.com/v1/token"
PARKALOT_RESERVE_URL = (
    "https://us-central1-project-3687381701726997562.cloudfunctions.net"
    "/reservationsservice/assign"
)

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


def renovar_token(refresh_token: str, api_key: str) -> str:
    """Intercambia el refresh token por un Firebase ID Token fresco (válido 1h)."""
    resp = httpx.post(
        f"{FIREBASE_TOKEN_URL}?key={api_key}",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Error renovando token: {resp.status_code} — {resp.text[:200]}")
    id_token = resp.json().get("id_token")
    if not id_token:
        raise RuntimeError(f"Respuesta sin id_token: {resp.text[:200]}")
    log.info("Token Firebase renovado ✓")
    return id_token


def reservar_via_api(token: str, spot_id: int, fecha: str, uid: str) -> bool:
    """
    Intenta reservar spot_id para la fecha dada.
    Retorna True si exitoso, False si el spot está ocupado (409/403).
    Lanza RuntimeError en errores no recuperables (401, 5xx persistente).

    Errores 5xx: reintenta una vez tras 1s antes de abortar.
    Error 401: aborta inmediatamente — no hay tiempo para re-login a las 16:00.
    """
    payload = {
        "day": fecha,
        "spotId": spot_id,
        "shifts": ["00002400"],
        "uid": uid,
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = httpx.post(PARKALOT_RESERVE_URL, json=payload, headers=headers, timeout=30)
    except httpx.TimeoutException:
        log.warning(f"Cochera {spot_id}: timeout — reintentando en 2s...")
        time.sleep(2)
        try:
            resp = httpx.post(PARKALOT_RESERVE_URL, json=payload, headers=headers, timeout=30)
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Timeout persistente al reservar cochera {spot_id}: {e}") from e

    if resp.status_code in (200, 201):
        log.info(f"✅ Cochera {spot_id} reservada para {fecha}")
        return True

    if resp.status_code in (409, 403):
        log.info(f"Cochera {spot_id} ocupada ({resp.status_code}) — intentando siguiente...")
        return False

    if resp.status_code == 401:
        raise RuntimeError(
            f"Token inválido (401) — abortando para no perder la ventana de las 16:00"
        )

    if resp.status_code >= 500:
        log.warning(f"Error de servidor {resp.status_code} en cochera {spot_id} — reintentando en 1s...")
        time.sleep(1)
        try:
            resp2 = httpx.post(PARKALOT_RESERVE_URL, json=payload, headers=headers, timeout=30)
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Timeout en reintento 5xx para cochera {spot_id}: {e}") from e
        if resp2.status_code in (200, 201):
            log.info(f"✅ Cochera {spot_id} reservada (reintento)")
            return True
        raise RuntimeError(f"Error de servidor persistente ({resp2.status_code}): {resp2.text[:200]}")

    raise RuntimeError(f"Respuesta inesperada ({resp.status_code}): {resp.text[:200]}")


def main():
    log.info("=" * 60)
    log.info("  Reserva automática de cochera — Parkalot")
    log.info("=" * 60)

    ahora = ahora_arg()
    log.info(f"Hora actual ARG: {ahora.strftime('%A %Y-%m-%d %H:%M:%S')}")

    if not debe_ejecutar_hoy():
        log.info(f"Hoy ({ahora.strftime('%A')}) no corresponde ejecutar. Finalizando.")
        sys.exit(0)

    for var, nombre in [
        (PARKALOT_REFRESH_TOKEN, "PARKALOT_REFRESH_TOKEN"),
        (PARKALOT_UID,           "PARKALOT_UID"),
        (PARKALOT_API_KEY,       "PARKALOT_API_KEY"),
    ]:
        if not var:
            log.error(f"Variable de entorno faltante: {nombre}")
            sys.exit(1)

    fecha = fecha_manana_str()
    log.info(f"Objetivo: reservar cochera para el {fecha}")
    log.info(f"Orden de prioridad: {COCHERAS_PRIORIDAD}")

    esperar_hasta_previa_apertura()

    try:
        token = renovar_token(PARKALOT_REFRESH_TOKEN, PARKALOT_API_KEY)
    except Exception as e:
        log.error(f"No se pudo obtener token: {e}")
        enviar_whatsapp(f"❌ Error de autenticación al reservar cochera para el {fecha}. Revisá el log.")
        sys.exit(1)

    limite = ahora_arg() + timedelta(minutes=TIMEOUT_ESPERA_MIN)
    reservado = False
    intentos = 0

    while ahora_arg() <= limite and not reservado:
        intentos += 1
        ahora_actual = ahora_arg()
        apertura = ahora_actual.replace(
            hour=HORA_APERTURA, minute=MINUTO_APERTURA, second=0, microsecond=0
        )

        seg_hasta_apertura = (apertura - ahora_actual).total_seconds()
        if seg_hasta_apertura > 0.05:
            espera = min(seg_hasta_apertura - 0.05, INTERVALO_REINTENTO_SEG)
            if espera > 1:
                log.info(f"Esperando apertura de las {apertura.strftime('%H:%M')} (faltan {seg_hasta_apertura:.0f}s)...")
            time.sleep(espera)
            continue

        log.info(f"[Intento #{intentos} — {ahora_actual.strftime('%H:%M:%S')} ARG]")

        try:
            for cochera in COCHERAS_PRIORIDAD:
                if reservar_via_api(token, cochera, fecha, PARKALOT_UID):
                    reservado = True
                    enviar_whatsapp(f"✅ Cochera {cochera} reservada para el {fecha} 🚗")
                    break
        except RuntimeError as e:
            log.error(f"Error en intento #{intentos}: {e}")
            enviar_whatsapp(f"❌ Error al reservar cochera para el {fecha}: {e}")
            sys.exit(1)

        if not reservado:
            log.info(f"Todas las cocheras prioritarias ocupadas en intento #{intentos}. Reintentando en 1s...")
            time.sleep(1)

    if not reservado:
        log.error(f"❌ No se pudo reservar luego de {intentos} intentos.")
        enviar_whatsapp(
            f"❌ No se pudo reservar cochera para el {fecha}. Revisá el log en GitHub Actions."
        )
        sys.exit(1)

    log.info("Script finalizado correctamente.")


if __name__ == "__main__":
    main()
