# 🚗 Reserva Automática de Cochera — Parkalot

Sistema que reserva automáticamente cocheras en Parkalot cada día hábil a las **16:00 (hora Argentina)**, sin que tengas que estar frente a la computadora.

---

## ¿Qué hace exactamente?

Parkalot habilita las reservas del día siguiente a las **16:00 ARG** en punto. En ese momento hay competencia: quien reserva primero se queda con la mejor cochera. Este sistema automatiza ese proceso.

**Qué hace el programa, paso a paso:**

1. A las **15:55 ARG** se activa automáticamente (de domingo a jueves)
2. Abre dos navegadores simultáneos con tu cuenta de Parkalot
3. Cada navegador se posiciona en una cochera prioritaria diferente antes de las 16:00
4. En el instante exacto de las **16:00:00**, ambos presionan el botón RESERVE al mismo tiempo
5. El primero que logre reservar gana — Parkalot cancela automáticamente el intento del otro
6. Si ninguno de los dos pudo reservar (cocheras tomadas), intenta con cualquier otra disponible
7. Te manda un mensaje de WhatsApp confirmando qué cochera quedó reservada (opcional)

**Orden de prioridad:**

| Sesión | Cochera | Ubicación |
|--------|---------|-----------|
| 1° (paralela) | **209** | 2do Subsuelo — Olivos |
| 2° (paralela) | **208** | 2do Subsuelo — Olivos |
| Fallback | **237** y cualquier disponible | — |

**Días de ejecución:**

| Corre este día | Reserva para |
|---------------|-------------|
| Domingo       | Lunes       |
| Lunes         | Martes      |
| Martes        | Miércoles   |
| Miércoles     | Jueves      |
| Jueves        | Viernes     |

---

## ¿Cómo funciona por dentro?

El sistema usa tres componentes que trabajan juntos:

```
cron-job.org  ──►  GitHub Actions  ──►  Playwright (browser automatizado)
 (reloj)           (servidor)            (hace los clicks en Parkalot)
```

- **cron-job.org**: Es el "despertador". A las 18:55 UTC (= 15:55 ARG) manda una señal a GitHub para activar el script. Se usa un servicio externo porque el reloj interno de GitHub puede atrasarse hasta 60 minutos.

- **GitHub Actions**: Es el servidor que corre el script en la nube, gratis. No necesitás dejar tu computadora encendida.

- **Playwright**: Es la librería que controla un navegador Chrome invisible, entra a Parkalot con tu usuario y contraseña, y hace los clicks en el momento exacto.

---

## Configuración paso a paso (para nuevos usuarios)

> No hace falta saber programar. Solo seguí estos pasos en orden.

### Paso 1 — Creá una cuenta en GitHub

GitHub es el servicio donde vive el código y donde se ejecuta el script.

1. Entrá a [github.com](https://github.com) y creá una cuenta gratuita
2. Verificá tu email

---

### Paso 2 — Copiá el repositorio a tu cuenta ("Fork")

Un "fork" es tu propia copia del proyecto donde podés configurar tus datos sin afectar el original.

1. Entrá a la página de este repositorio en GitHub
2. Hacé click en el botón **"Fork"** (arriba a la derecha)
3. Dejá todo como está y hacé click en **"Create fork"**

Ahora tenés tu propia copia en `github.com/TU_USUARIO/reserva-cochera`.

---

### Paso 3 — Guardá tus credenciales de Parkalot

El script necesita tu email y contraseña de Parkalot para poder loguearse. Estos datos se guardan de forma segura como "secrets" en GitHub — nadie más puede verlos.

1. En tu fork, andá a **Settings** (pestaña superior)
2. En el menú izquierdo: **Secrets and variables** → **Actions**
3. Hacé click en **"New repository secret"** y creá estos dos:

| Nombre exacto (copialo tal cual) | Valor |
|----------------------------------|-------|
| `PARKALOT_EMAIL` | Tu email de Parkalot |
| `PARKALOT_PASSWORD` | Tu contraseña de Parkalot |

**Opcional — notificaciones por WhatsApp:**

Si querés recibir un mensaje cuando se concrete la reserva, necesitás configurar CallMeBot. Seguí las instrucciones en [callmebot.com/blog/free-whatsapp-api](https://www.callmebot.com/blog/free-whatsapp-api/) y luego creá estos dos secrets adicionales:

| Nombre exacto | Valor |
|---------------|-------|
| `WHATSAPP_PHONE` | Tu número internacional sin `+` (ej: `5491112345678`) |
| `WHATSAPP_APIKEY` | La API key que te da CallMeBot |

---

### Paso 4 — Creá un token de acceso para GitHub

Este token le permite a cron-job.org activar el script en tu repositorio.

1. En GitHub: click en tu foto de perfil (arriba a la derecha) → **Settings**
2. Bajá hasta **Developer settings** (al final del menú izquierdo) → **Personal access tokens** → **Fine-grained tokens**
3. Click en **"Generate new token"**
4. Completá:
   - **Token name:** `cron-reserva-cochera`
   - **Expiration:** 1 year
   - **Repository access:** Solo tu fork de `reserva-cochera`
   - **Permissions → Repository permissions → Actions:** `Read and write`
5. Click en **"Generate token"**
6. **Copiá el token ahora** — solo se muestra una vez. Empieza con `github_pat_...`

---

### Paso 5 — Configurá el reloj automático en cron-job.org

1. Creá una cuenta gratuita en [cron-job.org](https://cron-job.org)
2. Click en **"Create cronjob"**
3. Completá el formulario:

**URL:**
```
https://api.github.com/repos/TU_USUARIO/reserva-cochera/actions/workflows/scheduler.yml/dispatches
```
> Reemplazá `TU_USUARIO` por tu nombre de usuario de GitHub

**Método:** `POST`

**Horario:** Hacé click en "Advanced" y usá esta expresión cron:
```
55 18 * * 0,1,2,3,4
```
> Esto significa: a las 18:55 UTC (= 15:55 ARG) los domingos, lunes, martes, miércoles y jueves

4. En la sección **Headers**, agregá estos tres:

| Key | Value |
|-----|-------|
| `Authorization` | `Bearer TU_TOKEN` (el token que generaste en el paso 4) |
| `Content-Type` | `application/json` |
| `Accept` | `application/vnd.github.v3+json` |

5. En **Request body**:
```json
{"ref": "main", "inputs": {"modo": "produccion"}}
```

6. Click en **"Create"**
7. Probá que funciona: click en **"Run now"** → debe aparecer `204 No Content` como respuesta

---

### Paso 6 — Verificá que todo funciona

La primera vez que se ejecute (al día siguiente hábil), podés ver qué pasó así:

1. En tu fork en GitHub → pestaña **Actions**
2. Hacé click en la ejecución más reciente
3. Expandí el job **"Reserva"** para ver los logs paso a paso
4. Al final del job vas a ver una sección **"Screenshots"** descargable con capturas de cada paso

---

## Archivos del proyecto

```
reserva-cochera/
├── reservar_cochera.py      → Script principal
├── requirements.txt         → Librerías Python necesarias
├── pytest.ini               → Configuración de tests
├── tests/
│   └── test_unit.py         → Tests automáticos de calidad
└── .github/
    └── workflows/
        └── scheduler.yml    → Configuración de GitHub Actions
```

---

## Solución de problemas

### ❌ El script se loguea pero no reserva nada

- Verificá que `PARKALOT_EMAIL` y `PARKALOT_PASSWORD` sean correctos
- Revisá los screenshots en la sección **Actions** para ver en qué paso falló
- Si cambiaste tu contraseña de Parkalot, actualizá el secret `PARKALOT_PASSWORD` en GitHub

### ❌ El workflow no se activa a las 16:00

- En cron-job.org verificá que el último run devolvió `204 No Content`
- Confirmá que el token de GitHub no expiró (duran 1 año por defecto)
- Revisá que la URL del webhook tenga tu nombre de usuario correcto

### ❌ El token de GitHub expiró

Repetí el Paso 4 para generar uno nuevo y actualizalo en cron-job.org.

---

## Personalización

### Cambiar el orden de prioridad de cocheras

Editá esta línea en `reservar_cochera.py`:
```python
COCHERAS_PRIORIDAD = [209, 208, 237]  # De mayor a menor preferencia
```

### Cambiar qué cocheras se intentan en paralelo

Editá esta línea en `main()` dentro de `reservar_cochera.py`:
```python
COCHERAS_PARALELAS = [209, 208]  # Estas dos se intentan al mismo tiempo a las 16:00
```

### Cambiar los días de ejecución

Editá en `reservar_cochera.py`:
```python
DIAS_EJECUCION = {6, 0, 1, 2, 3}  # Domingo=6, Lunes=0, Martes=1, Miércoles=2, Jueves=3
```
Y actualizá también el horario en cron-job.org.

### Cambiar la hora de apertura de reservas

Si Parkalot cambia la hora de apertura (actualmente 16:00 ARG), ajustá:
```python
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
```
Y en cron-job.org actualizá el horario para que dispare 5 minutos antes.
