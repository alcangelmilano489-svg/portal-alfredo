# Corrección de Contacto en producción

## Diagnóstico confirmado

Revisé el contenido de GitHub `master`, el último despliegue activo de Render y el HTML/API servidos por el dominio:

- El commit actual de `master` y Render es `1e03380e66896b33a64d99563b50aced003a5975` (`Corregir vista publica de contacto desde Supabase`). Ese commit solo añadió un archivo Markdown de guía; **no modificó `index.html`**.
- La plantilla de `master` y el sitio público aún contienen `id="form-contacto"` con Nombre, Correo y Mensaje.
- `GET /api/contacto-publico` sigue respondiendo **404**.
- En la versión publicada, `admin.html` aún guarda Contacto en `localStorage`; no existe una ruta del backend para escribir o leer la tabla `contacto_publico`.
- La tabla de Supabase `public.contacto_publico` existe, pero la consulta de comprobación no encontró filas.

Por eso cambiar únicamente la plantilla no bastaría: también faltaba crear el endpoint de lectura/escritura y conectar el panel. El parche adjunto completa ese flujo con escritura autenticada y lectura pública de solo lectura. **No ejecuta ninguna migración contra Supabase.**

## Estado de publicación

El parche pasó **11 pruebas** automatizadas, validación de sintaxis de Python/JavaScript y comprobaciones del contrato frontend/backend. Traté de actualizar `master`, pero GitHub respondió **403: permiso de escritura denegado** en las sesiones disponibles. El commit de corrección queda local; el dominio todavía no ha recibido este cambio.

## Aplicar sobre la rama actual

Descarga `portal-alfredo-contact-live-fix.patch` y guárdalo en la carpeta del repositorio. La base exacta es `1e03380e66896b33a64d99563b50aced003a5975`.

```bash
git switch master
git pull --ff-only origin master
git rev-parse HEAD
```

Confirma que el resultado sea el hash base indicado. Después aplica y prueba:

```bash
git apply --check portal-alfredo-contact-live-fix.patch
git apply portal-alfredo-contact-live-fix.patch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
git diff --check
git status --short
```

Publica solo los archivos previstos:

```bash
git add admin.html index.html migrations/20261002_contacto_publico.sql servidor.py style.css tests/test_contact_api.py
git commit -m "Render public contact channels from Supabase"
git push origin master
```

Render tiene auto-deploy desde `master`; espera el nuevo despliegue antes de verificar el dominio. Si tu cuenta también rechaza el `push`, usa la interfaz de GitHub para subir estos cambios al `master` o comparte el error que aparezca. No hace falta cambiar secretos de Render.

## Verificación posterior

1. Comprueba que `https://www.alfredomaneiro.org.ve/api/contacto-publico` deje de responder 404 y devuelva JSON `success: true`.
2. Abre `/admin` en el mismo navegador habitual. El panel nuevo puede rescatar los valores locales anteriores como borrador; pulsa **Guardar Redes y Contacto** para persistirlos de forma real en Supabase.
3. Abre la sección pública **Contacto** y confirma que aparezcan las tarjetas con los canales no vacíos.

La migración SQL está incluida para documentar el esquema en el repositorio, pero la tabla ya existe en el proyecto activo: **no vuelvas a ejecutar esa migración allí**.
