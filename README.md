# 🚗 Reserva Automática de Cochera — Parkalot

Sistema que reserva automáticamente cocheras en Parkalot cada día hábil a las **16:00 (hora Argentina)**, usando **GitHub Actions** como servidor gratuito en la nube.

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
- Reintenta cada 5 segundos hasta las 16:10 si la reserva aún no está disponible

---

## Archivos del proyecto

```
reserva-cochera/
├── reservar_cochera.py          → Script principal (producción)
├── test_reserva.py              → Script de prueba (reserva inmediata, sin esperar 16:00)
└── .github/
    └── workflows/
        └── scheduler.yml        → Programación automática en GitHub Actions
```

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

#### Subir `reservar_cochera.py` y `test_reserva.py`
1. Click en **"Add file" → "Upload files"**
2. Arrastrá ambos archivos juntos
3. Click en **"Commit changes"**

#### Crear el workflow
1. Click en **"Add file" → "Create new file"**
2. En el nombre escribí exactamente: `.github/workflows/scheduler.yml`
3. Pegá el contenido del archivo `scheduler.yml`
4. Click en **"Commit new file"**

---

### Paso 4 — Guardar credenciales de forma segura

1. En tu repositorio → **Settings** → **Secrets and variables** → **Actions**
2. Click en **"New repository secret"** y creá estos dos:

| Nombre exacto       | Valor                     |
|--------------------|--------------------------|
| `PARKALOT_EMAIL`   | Tu email de Parkalot     |
| `PARKALOT_PASSWORD`| Tu contraseña de Parkalot|

Los valores quedan encriptados — nadie puede verlos una vez guardados.

---

### Paso 5 — Probar que funciona

1. Ir a la pestaña **Actions** de tu repositorio
2. Click en **"Reserva Automática Cochera"**
3. Click en **"Run workflow"**
4. En el desplegable elegir **`test`**
5. Click en el botón verde **"Run workflow"**
6. Esperá ~2 minutos y verificá el resultado:
   - ✅ Verde = reserva exitosa
   - ❌ Rojo = algo falló, click para ver el log

#### Ver los screenshots de cada ejecución
1. **Actions** → click en la ejecución más reciente
2. Al final de la página → sección **"Artifacts"**
3. Descargar el zip con los screenshots de cada paso

---

## Solución de problemas

### ❌ Error en el login
- Verificá los Secrets en Settings — no deben tener espacios
- Probá loguearte manualmente en [app.parkalot.io](https://app.parkalot.io)

### ❌ No encuentra las cocheras
Parkalot puede actualizar su interfaz. Descargá el screenshot del error para ver en qué pantalla falló.

### ⚠️ Cambiar el orden de prioridad de cocheras
En `reservar_cochera.py` y `test_reserva.py`, modificá esta línea:
```python
COCHERAS_PRIORIDAD = [237, 209, 208, 238]
```

### ⚠️ Cambiar los días de reserva
En `reservar_cochera.py`:
```python
DIAS_EJECUCION = {6, 0, 1, 3}  # Domingo=6, Lunes=0, Martes=1, Jueves=3
```
En `scheduler.yml`:
```yaml
- cron: "55 18 * * 0,1,2,4"   # Dom=0, Lun=1, Mar=2, Jue=4 (en cron UTC)
```

### ⚠️ Cambiar el horario de apertura de reservas
Si Parkalot cambia la hora de apertura (deja de ser 16:00), ajustá en `reservar_cochera.py`:
```python
HORA_APERTURA   = 16
MINUTO_APERTURA = 0
```
Y en `scheduler.yml` el cron para que arranque 5 minutos antes.

---

## Arquitectura del sistema

```
GitHub Actions (servidor gratuito en la nube)
│
├── scheduler.yml
│   └── Cron: Dom/Lun/Mar/Jue a las 18:55 UTC (15:55 ARG)
│
└── reservar_cochera.py
    ├── 15:55 → Login en Parkalot
    ├── 15:55–16:00 → Espera activa (reintenta cada 5s)
    ├── 16:00 → Click en DETAILS del día siguiente
    │           (siempre el último botón DETAILS visible)
    ├── Busca cocheras por orden de prioridad: 237 → 209 → 208 → 238
    ├── Si ninguna está disponible → reserva la primera de la lista
    └── Click en RESERVE → Confirmación
```
