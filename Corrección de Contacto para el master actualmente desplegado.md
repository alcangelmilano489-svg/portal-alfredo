# Corrección de Contacto para el master actualmente desplegado

## Hallazgo de producción

El dominio estaba sirviendo el formulario antiguo y `GET /api/contacto-publico` respondía **404**. También comprobé el código de `master` que Render despliega: el panel `/admin` guardaba los valores de Contacto en `localStorage`, no en Supabase. La tabla `public.contacto_publico` existe en el proyecto activo, tiene RLS correcto, pero **no contiene ninguna fila**. El último deploy de Render sí estaba marcado como activo, por lo que no era solo un despliegue que siguiera procesándose: faltaban las rutas y el renderizado en el código de esa versión.

Por eso el parche no cambia solo el HTML. Completa el flujo: panel admin → backend con autenticación → Supabase → vista pública estructurada. También valida los enlaces y mantiene acceso público de solo lectura.

## Parche y base exacta

El archivo `portal-alfredo-contact-frontend-fix.patch` se preparó contra `master` en el commit:

```text
beb4d9ecb433aed150575c308a4fd125a4cd40ee
```

La migración de `contacto_publico` **ya está aplicada** al proyecto Supabase activo. El SQL incluido es para dejar el esquema versionado; no la vuelvas a ejecutar allí.

## Aplicar y desplegar

En una terminal donde tengas el repositorio:

```bash
git switch master
git pull --ff-only origin master
git rev-parse HEAD
```

Confirma que el resultado sea `beb4d9ecb433aed150575c308a4fd125a4cd40ee`. Guarda el parche adjunto en esa carpeta y ejecuta:

```bash
git apply --check portal-alfredo-contact-frontend-fix.patch
git apply portal-alfredo-contact-frontend-fix.patch
```

Corre las pruebas y revisa los cambios:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
git diff --check
git status --short
```

Se esperan **11 pruebas aprobadas**. Para publicar:

```bash
git add admin.html index.html migrations/20261002_contacto_publico.sql servidor.py style.css tests/test_contact_api.py
git commit -m "Show public contact channels from Supabase"
git push origin master
```

El servicio Render `portal-alfredo` está conectado a `master` con auto-deploy. Espera que el despliegue del nuevo commit termine antes de probar el dominio. No se necesitan cambios de variables secretas ni una nueva migración de base de datos.

## Después del deploy

Abre `/admin` en el mismo navegador que usabas antes. Si los valores antiguos siguen en su `localStorage`, el nuevo panel los cargará como borrador cuando no encuentre datos en Supabase. Pulsa **Guardar Redes y Contacto** y espera el mensaje que confirma que se guardaron en Supabase. Luego abre la sección **Contacto** en la página pública; aparecerán las tarjetas configuradas para WhatsApp, correo, Messenger y TikTok. Los campos vacíos no se muestran.

Si el panel no recupera los valores del navegador anterior, introdúcelos nuevamente y guárdalos. La inspección de la tabla mostró que no había una fila persistida.
