"""
Script de PRUEBA — Reserva real en Parkalot via API httpx.
Intenta reservar para mañana de inmediato, sin esperar las 16:00.
Orden de prioridad: según COCHERAS_PRIORIDAD.
"""

import sys
import logging

from reservar_cochera import (
    PARKALOT_REFRESH_TOKEN, PARKALOT_UID, PARKALOT_API_KEY,
    COCHERAS_PRIORIDAD,
    renovar_token, reservar_via_api, TokenInvalidoError,
    fecha_manana_str, enviar_whatsapp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def main():
    log.info("=" * 60)
    log.info("  TEST — Reserva real inmediata (sin espera de horario)")
    log.info("=" * 60)

    for var, nombre in [
        (PARKALOT_REFRESH_TOKEN, "PARKALOT_REFRESH_TOKEN"),
        (PARKALOT_UID,           "PARKALOT_UID"),
        (PARKALOT_API_KEY,       "PARKALOT_API_KEY"),
    ]:
        if not var:
            log.error(f"Variable de entorno faltante: {nombre}")
            sys.exit(1)

    fecha = fecha_manana_str()
    log.info(f"Reservando para: {fecha}")
    log.info(f"Orden de prioridad: {COCHERAS_PRIORIDAD}")

    log.info("Obteniendo token Firebase...")
    try:
        token = renovar_token(PARKALOT_REFRESH_TOKEN, PARKALOT_API_KEY)
    except Exception as e:
        log.error(f"No se pudo obtener token: {e}")
        enviar_whatsapp(f"❌ Test fallido — error de autenticación: {e}")
        sys.exit(1)

    reservado = False
    for cochera in COCHERAS_PRIORIDAD:
        log.info(f"Intentando cochera {cochera}...")
        try:
            if reservar_via_api(token, cochera, fecha, PARKALOT_UID):
                reservado = True
                log.info(f"✅ Cochera {cochera} reservada para {fecha}")
                enviar_whatsapp(f"✅ [TEST] Cochera {cochera} reservada para el {fecha} 🚗")
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
        enviar_whatsapp(f"❌ [TEST] No se pudo reservar ninguna cochera para {fecha}.")
        sys.exit(1)

    log.info("✅ Test finalizado correctamente.")


if __name__ == "__main__":
    main()
