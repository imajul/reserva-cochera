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
| 1°        | 237     |
| 2°        | 209     |
| 3°        | 208     |
| 4°        | 238     |
| 5°        | Primera disponible en la lista |

**Estrategia de ejecución:**
- Arranca a las **15:55 ARG** y hace login
- Espera activamente hasta las **16:00** en que se habilitan las reservas
- En cuanto se habilitan, intenta reservar según el orden de prioridad
- Si aparecen dos tarjetas de días (hoy + mañana), siempre selecciona la del **día siguiente**
- Reintenta cada 5 segundos durante 10 minutos si la reserva aún no está disponible

---

## Archivos del proyecto

```
reserva-cochera/
├── reservar_cochera.py          → Script principal (producción)
├── test_reserva.py              → Script de prueba (reserva inmediata, sin esperar 16:00)
├── requirements.txt             → Dependencias Python
├── pytest.ini                   → Configuración de tests
├── tests/
│   ├── conftest.py              → Mock de Playwright para tests unitarios
│   └── test_unit.py             → 26 tests unitarios
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
├── Job: Tests unitarios (26 tests — gate de calidad)
│
└── Job: Reserva (modo produccion / test)
    └── reservar_cochera.py
        ├── 15:55 → Login en Parkalot
        ├── 15:55–16:00 → Espera activa
        ├── 16:00 → Click en DETAILS del día siguiente
        ├── Busca cocheras: 237 → 209 → 208 → 238 → primera disponible
        └── Click en RESERVE → Confirmación
```

> **¿Por qué cron-job.org y no el cron interno de GitHub Actions?**
> GitHub Actions puede demorar 30–60 minutos en ejecutar un cron programado bajo alta carga. Como la ventana de reserva de Parkalot abre exactamente a las 16:00, cualquier demora significa perder el turno. cron-job.org garantiza la llamada puntual al minuto.

---

## Configuración paso a paso

### Paso 1 — Crear cuenta en GitHub
Si no tenés, creá una gratis en [github.com](https://github.com).

---

### Paso 2 — Crear un repositorio privado

1. Click en **"+" → "New repository"**
2. Nombre: `reserva-cochera`
3. Seleccioná **"Private"** ⚠️
4. Click en **"Create repository"**

---

### Paso 3 — Subir los archivos

1. Click en **"Add file" → "Upload files"**
2. Subí todos los archivos del proyecto
3. Click en **"Commit changes"**

---

### Paso 4 — Guardar credenciales de Parkalot

1. En tu repositorio → **Settings** → **Secrets and variables** → **Actions**
2. Click en **"New repository secret"** y creá estos dos:

| Nombre exacto        | Valor                      |
|---------------------|---------------------------|
| `PARKALOT_EMAIL`    | Tu email de Parkalot      |
| `PARKALOT_PASSWORD` | Tu contraseña de Parkalot |

Los valores quedan encriptados — nadie puede verlos una vez guardados.

---

### Paso 5 — Configurar cron-job.org

#### 5a — Crear un GitHub Personal Access Token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click en **"Generate new token"**
3. Completá:
   - **Token name:** `cron-job-reserva-cochera`
   - **Expiration:** 1 año
   - **Repository access:** Only select repositories → `reserva-cochera`
   - **Permissions → Repository permissions → Actions:** `Read and write`
4. Click en **"Generate token"** y guardalo en un gestor de contraseñas (se muestra una sola vez)

#### 5b — Crear el cron en cron-job.org

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

5. Click en **"Create"**
6. Probá con **"Run now"** → debe responder `204 No Content`

---

### Paso 6 — Verificar que funciona

Para una prueba manual sin esperar el horario:

1. Ir a la pestaña **Actions** del repositorio
2. Click en **"Reserva Automática Cochera"** → **"Run workflow"**
3. Elegir **`test`** y click en el botón verde
4. Esperá ~2 minutos y verificá el resultado:
   - ✅ Verde = reserva exitosa
   - ❌ Rojo = algo falló, click para ver el log

Los screenshots de cada ejecución se guardan como artefactos en el run (sección **Artifacts** al final de cada ejecución).

---

## Solución de problemas

### ❌ Error en el login
- Verificá los Secrets en Settings — no deben tener espacios extra
- Probá loguearte manualmente en [app.parkalot.io](https://app.parkalot.io)

### ❌ No encuentra las cocheras
Parkalot puede actualizar su interfaz. Descargá el screenshot del error para ver en qué pantalla falló.

### ❌ El workflow no se dispara a las 16:00
- Verificá en cron-job.org que el último run devolvió `204 No Content`
- Confirmá que el token no expiró (duran 1 año por defecto)
- Revisá que la URL del webhook tenga tu usuario correcto

### ⚠️ Cambiar el orden de prioridad de cocheras
En `reservar_cochera.py`:
```python
COCHERAS_PRIORIDAD = [237, 209, 208, 238]
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
