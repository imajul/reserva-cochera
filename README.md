# 🚗 Reserva Automática de Cochera — Parkalot

Sistema que reserva automáticamente la **cochera 237** en Parkalot cada día hábil,
usando **GitHub Actions** como servidor gratuito en la nube.

---

## ¿Cómo funciona?

```
15:55 ARG  →  El script arranca en la nube
15:55–16:00 →  Espera activa: intenta cada 5 segundos
16:00:00   →  En cuanto se habilita, reserva inmediatamente la cochera 237
               Si está ocupada → reserva la más cercana disponible
16:10      →  Si no logró reservar en 10 minutos, registra el error
```

| Día en que corre | Reserva para |
|-----------------|-------------|
| Lunes 15:55     | Martes      |
| Martes 15:55    | Miércoles   |
| Jueves 15:55    | Viernes     |

*(Los miércoles también corre pero el script lo ignora porque el jueves no está en tu lista)*

---

## Configuración paso a paso

### Paso 1 — Crear cuenta en GitHub
Si no tenés, creá una gratis en [github.com](https://github.com). Es gratuito.

---

### Paso 2 — Crear un repositorio privado

1. En GitHub, click en **"+" → "New repository"**
2. Nombre: `reserva-cochera`
3. Seleccioná **"Private"** ⚠️ (importante para proteger tus credenciales)
4. Click en **"Create repository"**

---

### Paso 3 — Subir los archivos

#### Subir `reservar_cochera.py`
1. En tu repositorio, click en **"Add file" → "Upload files"**
2. Arrastrá el archivo `reservar_cochera.py`
3. Click en **"Commit changes"**

#### Crear el workflow de GitHub Actions
1. Click en **"Add file" → "Create new file"**
2. En el campo de nombre escribí exactamente: `.github/workflows/scheduler.yml`
   *(GitHub crea las carpetas automáticamente)*
3. Copiá y pegá el contenido del archivo `scheduler.yml` que te entregamos
4. Click en **"Commit new file"**

---

### Paso 4 — Guardar tus credenciales de forma segura

Tus credenciales se guardan **encriptadas** en GitHub, nunca en el código.

1. En tu repositorio → **Settings** (engranaje, arriba a la derecha)
2. Menú izquierdo: **"Secrets and variables" → "Actions"**
3. Click en **"New repository secret"** y creá estos dos:

| Nombre exacto del Secret | Valor a poner              |
|--------------------------|---------------------------|
| `PARKALOT_EMAIL`         | Tu email de Parkalot      |
| `PARKALOT_PASSWORD`      | Tu contraseña de Parkalot |

---

### Paso 5 — Probar manualmente (recomendado antes del primer día)

1. Ir a la pestaña **"Actions"** de tu repositorio
2. En la lista izquierda: **"Reserva Automática Cochera 237"**
3. Click en **"Run workflow"** (botón gris a la derecha)
4. Click en el botón verde **"Run workflow"**
5. Esperá ~2 minutos y verificá el resultado:
   - ✅ Verde = éxito
   - ❌ Rojo = algo falló, hacer click para ver el log detallado

---

### Paso 6 — Revisar el screenshot de resultado

Después de cada ejecución (exitosa o no), el script guarda un screenshot:

1. **"Actions"** → click en la ejecución más reciente
2. Al final de la página → sección **"Artifacts"**
3. Descargar **"screenshot-XXXXX"**

Esto te permite ver exactamente en qué pantalla se quedó el script.

---

## Solución de problemas

### ❌ Error: credenciales inválidas
- Verificá los Secrets en Settings → no deben tener espacios al inicio o final
- Probá loguearte manualmente en [app.parkalot.io](https://app.parkalot.io)

### ❌ El script no encuentra las cocheras
Parkalot puede actualizar su interfaz. Descargá el screenshot del error para
ver en qué pantalla falló y abrí un issue o modificá los selectores CSS en
`reservar_cochera.py` según lo que veas.

### ⚠️ El horario de apertura cambia
Si Parkalot cambia la hora de apertura (deja de ser 16:00), ajustá:

**En `scheduler.yml`** — el cron de arranque:
```yaml
- cron: "55 18 * * 1-4"   # 18:55 UTC = 15:55 ARG
```

**En `reservar_cochera.py`** — la hora de apertura:
```python
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
```

### ⚠️ Quiero agregar o quitar días
En `reservar_cochera.py`, modificá:
```python
DIAS_RESERVA = {0, 1, 2, 4}  # Lunes=0, Martes=1, Miércoles=2, Jueves=3, Viernes=4
```

---

## Arquitectura del sistema

```
GitHub Actions (servidor gratuito en la nube)
│
├── scheduler.yml      → Programa la ejecución automática (cron)
│                        Lunes–Jueves a las 15:55 ARG
│
└── reservar_cochera.py → Script principal
    │
    ├── Espera hasta las 15:59:50 (sleep)
    ├── Login en Parkalot
    └── Loop cada 5s hasta las 16:10:
        ├── ¿Está disponible la 237? → Reservar ✅
        ├── ¿Está ocupada?           → Reservar la más cercana ✅
        └── ¿No hay nada aún?        → Reintentar en 5s 🔄
```
