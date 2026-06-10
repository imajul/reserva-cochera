# 🚗 Reserva Automática de Cochera — Parkalot

Sistema que reserva automáticamente cocheras en Parkalot cada día hábil a las **16:00 (hora Argentina)**, usando **cron-job.org** como scheduler externo y **GitHub Actions** como servidor de ejecución.

---

## ¿Qué hace exactamente?

| Día en que corre | Reserva para |
|-----------------|-------------|
| Domingo 15:55   | Lunes       |
| Lunes 15:55     | Martes      |
| Martes 15:55    | Miércoles   |
| Jueves 15:55    | Viernes     |

**Orden de prioridad de cocheras:**

| Prioridad | Cochera |
|-----------|---------|
| 1°        | 209     |
| 2°        | 208     |
| 3°        | 237     |

**Estrategia de ejecución:**
- Arranca a las **15:55 ARG** y renueva el token de Firebase
- Espera activamente hasta las **16:00** en que se habilitan las reservas
- A las 16:00 llama directamente a la API de Parkalot (sin browser) en orden de prioridad
- Si una cochera está ocupada, pasa a la siguiente en ~200ms
- Reintenta cada 5 segundos durante 10 minutos si la reserva aún no está disponible

---

## Archivos del proyecto

```
reserva-cochera/
├── reservar_cochera.py          → Script principal (producción)
├── requirements.txt             → Dependencias Python (httpx, pytz)
├── pytest.ini                   → Configuración de tests
├── tests/
│   └── test_unit.py             → Tests unitarios
└── .github/
    └── workflows/
        └── scheduler.yml        → Workflow de GitHub Actions
```

---

## Arquitectura del sistema

```
cron-job.org (scheduler externo — puntualidad garantizada)
│
│  Dom/Lun/Mar/Jue a las 18:55 UTC (15:55 ARG)
│  POST https://api.github.com/repos/.../actions/workflows/scheduler.yml/dispatches
│
▼
GitHub Actions (servidor de ejecución)
│
├── Job: Tests unitarios (gate de calidad)
│
└── Job: Reserva (modo produccion / test)
    └── reservar_cochera.py
        ├── 15:55 → Renueva Firebase ID Token via securetoken.googleapis.com
        ├── 15:55–16:00 → Espera activa
        └── 16:00 → POST directo a Cloud Function de Parkalot
                      209 → si ocupada → 208 → si ocupada → 237
                      Éxito: WhatsApp de confirmación
                      Fallo total: WhatsApp de alerta + exit 1
```

> **¿Por qué cron-job.org y no el cron interno de GitHub Actions?**
> GitHub Actions puede demorar 30–60 minutos en ejecutar un cron programado bajo alta carga. Como la ventana de reserva de Parkalot abre exactamente a las 16:00, cualquier demora significa perder el turno. cron-job.org garantiza la llamada puntual al minuto.

> **¿Por qué llamada HTTP directa y no automatización de browser?**
> Parkalot usa Firebase + Cloud Functions como backend. Llamar directamente a la API elimina la dependencia del DOM, el scroll virtual de MUI, y el tiempo de carga del browser. La reserva se hace en ~1 segundo en lugar de ~20 segundos.

---

## Configuración para quien clona este repositorio

Si querés que funcione en tu cuenta, necesitás hacer estas 3 cosas — el código ya está listo.

### 1 — Forkeá el repositorio

1. Entrá al repositorio en GitHub
2. Click en **"Fork"** (arriba a la derecha)
3. Seleccioná tu cuenta como destino → **"Create fork"**

---

### 2 — Obtené tus credenciales de Parkalot

Necesitás tres valores de tu cuenta. Para obtenerlos:

1. Abrí Chrome y logueate en [app.parkalot.io](https://app.parkalot.io)
2. Abrí DevTools (F12) → pestaña **Application** → **IndexedDB** → **firebaseLocalStorageDb** → **firebaseLocalStorage**
3. Click en el registro que aparece y expandí el objeto `value`:

| Dato | Dónde encontrarlo |
|------|-------------------|
| `uid` | `value.uid` |
| `refreshToken` | `value.stsTokenManager.refreshToken` |
| `apiKey` | `value.apiKey` (empieza con `AIza...`) |

Luego, en tu fork → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Nombre exacto              | Valor                          |
|---------------------------|-------------------------------|
| `PARKALOT_REFRESH_TOKEN`  | El `refreshToken` obtenido     |
| `PARKALOT_UID`            | El `uid` obtenido              |
| `PARKALOT_API_KEY`        | El `apiKey` obtenido           |
| `WHATSAPP_PHONE`          | Tu número (ej: `5491112345678`) — opcional |
| `WHATSAPP_APIKEY`         | Tu API key de CallMeBot — opcional |

---

### 3 — Configurá tu propio cron-job.org

Necesitás tu propio scheduler porque el de quien te compartió el repo apunta a su repositorio, no al tuyo.

#### 3a — Crear un GitHub Personal Access Token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click en **"Generate new token"**
3. Completá:
   - **Token name:** `cron-job-reserva-cochera`
   - **Expiration:** 1 año
   - **Repository access:** Only select repositories → tu fork de `reserva-cochera`
   - **Permissions → Repository permissions → Actions:** `Read and write`
4. Click en **"Generate token"** y guardalo (se muestra una sola vez)

#### 3b — Crear el cron en cron-job.org

1. Creá una cuenta gratuita en [cron-job.org](https://cron-job.org)
2. Click en **"Create cronjob"** y completá:

| Campo | Valor |
|-------|-------|
| **URL** | `https://api.github.com/repos/TU_USUARIO/reserva-cochera/actions/workflows/scheduler.yml/dispatches` |
| **Método** | `POST` |
| **Horario** | `55 18 * * 0,1,2,4` |

3. En **Headers**, agregá estos tres:

| Key | Value |
|-----|-------|
| `Authorization` | `Bearer TU_TOKEN` |
| `Content-Type` | `application/json` |
| `Accept` | `application/vnd.github.v3+json` |

4. En **Request body**:
```json
{"ref": "main", "inputs": {"modo": "produccion"}}
```

5. Click en **"Create"** y probá con **"Run now"** → debe responder `204 No Content`

---

## Solución de problemas

### ❌ Error de autenticación (token inválido)
El `refreshToken` de Firebase puede ser revocado si cambiás tu contraseña de Parkalot o cerrás sesión en todos los dispositivos. En ese caso:
1. Logueate de nuevo en [app.parkalot.io](https://app.parkalot.io)
2. Extraé el nuevo `refreshToken` desde DevTools (mismo proceso que en el paso 2)
3. Actualizá el secret `PARKALOT_REFRESH_TOKEN` en GitHub

### ❌ El workflow no se dispara a las 16:00
- Verificá en cron-job.org que el último run devolvió `204 No Content`
- Confirmá que el GitHub token no expiró (duran 1 año por defecto)
- Revisá que la URL del webhook tenga tu usuario correcto

### ⚠️ Cambiar el orden de prioridad de cocheras
En `reservar_cochera.py`:
```python
COCHERAS_PRIORIDAD = [209, 208, 237]  # De mayor a menor preferencia
```

### ⚠️ Cambiar los días de reserva
En `reservar_cochera.py`:
```python
DIAS_EJECUCION = {6, 0, 1, 3}  # Domingo=6, Lunes=0, Martes=1, Jueves=3
```
Y en cron-job.org actualizá el horario correspondiente.

### ⚠️ Cambiar el horario de apertura de reservas
Si Parkalot cambia la hora de apertura (deja de ser 16:00), ajustá en `reservar_cochera.py`:
```python
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
```
Y en cron-job.org actualizá el horario para que dispare 5 minutos antes.
