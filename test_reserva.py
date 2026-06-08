"""
Script de PRUEBA — Reserva real en Parkalot via API httpx.
Intenta reservar para HOY de inmediato, sin esperar las 16:00.
Orden de prioridad: según COCHERAS_PRIORIDAD.
"""

import sys
import json
import base64
import logging
from datetime import date

from reservar_cochera import (
    PARKALOT_REFRESH_TOKEN, PARKALOT_UID, PARKALOT_API_KEY,
    COCHERAS_PRIORIDAD, TZ_ARG,
    renovar_token, reservar_via_api, TokenInvalidoError,
    enviar_whatsapp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata para HOY")
    log.info("=" * 60)

    for var, nombre in [
        (PARKALOT_REFRESH_TOKEN, "PARKALOT_REFRESH_TOKEN"),
        (PARKALOT_UID,           "PARKALOT_UID"),
        (PARKALOT_API_KEY,       "PARKALOT_API_KEY"),
    ]:
        if not var:
            log.error(f"Variable de entorno faltante: {nombre}")
            sys.exit(1)

    from datetime import datetime
    fecha = datetime.now(TZ_ARG).date().isoformat()  # hoy en hora ARG
    log.info(f"Reservando para: {fecha} (HOY)")
    log.info(f"Orden de prioridad: {COCHERAS_PRIORIDAD}")

    log.info("Obteniendo token Firebase...")
    try:
        token = renovar_token(PARKALOT_REFRESH_TOKEN, PARKALOT_API_KEY)
    except Exception as e:
        log.error(f"No se pudo obtener token: {e}")
        enviar_whatsapp(f"❌ Test fallido — error de autenticación: {e}")
        sys.exit(1)

    # Decodificar el JWT para comparar el UID embebido con PARKALOT_UID
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding
        jwt_payload = json.loads(base64.b64decode(payload_b64))
        uid_en_token = jwt_payload.get("user_id") or jwt_payload.get("sub", "?")
        log.info(f"UID en JWT (Firebase):  '{uid_en_token}'")
        log.info(f"PARKALOT_UID (secreto): '{PARKALOT_UID}'")
        if uid_en_token != PARKALOT_UID:
            log.warning("⚠️  LOS UIDs NO COINCIDEN — este es el motivo del 401")
        else:
            log.info("✅ UIDs coinciden")
    except Exception as e:
        log.warning(f"No se pudo decodificar JWT: {e}")

    reservado = False
    for cochera in COCHERAS_PRIORIDAD:
        log.info(f"Intentando cochera {cochera}...")
        try:
            if reservar_via_api(token, cochera, fecha, PARKALOT_UID):
                reservado = True
                log.info(f"✅ Cochera {cochera} reservada para {fecha}")
                enviar_whatsapp(f"✅ [TEST] Cochera {cochera} reservada para hoy {fecha} 🚗")
                break
            else:
                log.info(f"Cochera {cochera} ocupada — siguiente...")
        except TokenInvalidoError as e:
            log.error(f"Token rechazado (401): {e}")
            enviar_whatsapp(f"❌ Test fallido — token rechazado (401). Revisá el log.")
            sys.exit(1)
        except Exception as e:
            log.error(f"Error en cochera {cochera}: {e}")

    if not reservado:
        log.error("❌ Todas las cocheras de la lista están ocupadas o no disponibles.")
        enviar_whatsapp(f"❌ [TEST] No se pudo reservar ninguna cochera para hoy {fecha}.")
        sys.exit(1)

    log.info("✅ Test finalizado correctamente.")


if __name__ == "__main__":
    main()

