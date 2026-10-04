import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import httpx
from flask import Flask, jsonify, request, send_from_directory
from supabase import create_client
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


# ============================================================
# APLICACIÓN
# ============================================================

app = Flask(__name__)


# ============================================================
# CONFIGURACIÓN
# ============================================================

SUPABASE_URL = (
    os.environ.get("SUPABASE_URL") or ""
).strip().rstrip("/")

SUPABASE_ANON_KEY = (
    os.environ.get("SUPABASE_ANON_KEY") or ""
).strip()

SUPABASE_WRITE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
).strip()

# También permite usar la nueva variable de Supabase.
if not SUPABASE_WRITE_KEY:
    SUPABASE_WRITE_KEY = (
        os.environ.get("SUPABASE_SECRET_KEY") or ""
    ).strip()

ADMIN_PASSWORD = (
    os.environ.get("ADMIN_PASSWORD") or ""
).strip()

SUPABASE_STORAGE_BUCKET = (
    os.environ.get("SUPABASE_STORAGE_BUCKET") or "media"
).strip()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

SECCIONES_EDITORIALES = {
    "vida",
    "obra"
}


# ============================================================
# ARCHIVOS PÚBLICOS
# ============================================================

PUBLIC_ASSETS = {
    "style.css",
    "alfredo.png",
    "logo_siembra.jpeg",
    "maneiro2.jpeg",
    "maneiro3.jpeg",
    "maneiro4.jpeg",
    "maneiro5.jpeg",
    "maneiro7.jpeg",
    "maneiro8.jpeg",
    "neiro1.jpeg",
}


# ============================================================
# FORMATOS MULTIMEDIA PERMITIDOS
# ============================================================

ALLOWED_MEDIA = {
    ".gif": ("image/gif", "image"),
    ".jpeg": ("image/jpeg", "image"),
    ".jpg": ("image/jpeg", "image"),
    ".png": ("image/png", "image"),
    ".webp": ("image/webp", "image"),

    ".m4v": ("video/x-m4v", "video"),
    ".mov": ("video/quicktime", "video"),
    ".mp4": ("video/mp4", "video"),
    ".webm": ("video/webm", "video"),
}


# ============================================================
# INICIALIZACIÓN DE SUPABASE
# ============================================================

SUPABASE_CONFIG_ERROR = None

supabase = None
supabase_admin = None

if not SUPABASE_URL:

    SUPABASE_CONFIG_ERROR = (
        "Falta configurar SUPABASE_URL."
    )

elif not SUPABASE_ANON_KEY:

    SUPABASE_CONFIG_ERROR = (
        "Falta configurar SUPABASE_ANON_KEY."
    )

else:

    try:

        supabase = create_client(
            SUPABASE_URL,
            SUPABASE_ANON_KEY
        )

        if SUPABASE_WRITE_KEY:

            supabase_admin = create_client(
                SUPABASE_URL,
                SUPABASE_WRITE_KEY
            )

    except Exception as error:

        app.logger.exception(
            "No se pudo inicializar Supabase."
        )

        SUPABASE_CONFIG_ERROR = (
            f"No se pudo inicializar Supabase: {error}"
        )


# ============================================================
# RESPUESTA DE ERROR
# ============================================================

def respuesta_error(
    mensaje: str,
    estado: int
):

    return jsonify({
        "success": False,
        "error": str(mensaje)
    }), estado


# ============================================================
# HEADERS PARA SUPABASE
# ============================================================

def encabezados_supabase_admin():

    if not SUPABASE_WRITE_KEY:

        raise RuntimeError(
            "Falta configurar "
            "SUPABASE_SERVICE_ROLE_KEY "
            "o SUPABASE_SECRET_KEY."
        )

    headers = {
        "apikey": SUPABASE_WRITE_KEY
    }

    # Las claves antiguas JWT necesitan Authorization.
    # Las nuevas sb_secret_ NO deben enviarse como Bearer.

    if not SUPABASE_WRITE_KEY.startswith(
        "sb_secret_"
    ):

        headers["Authorization"] = (
            f"Bearer {SUPABASE_WRITE_KEY}"
        )

    return headers


# ============================================================
# PETICIÓN REST A SUPABASE
# ============================================================

def solicitar_supabase_admin(
    metodo: str,
    recurso: str,
    prefer: str = "return=representation",
    **kwargs
):

    headers = encabezados_supabase_admin()

    headers["Content-Type"] = (
        "application/json"
    )

    headers["Prefer"] = prefer

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{recurso}"
    )

    response = httpx.request(
        metodo,
        url,
        headers=headers,
        timeout=60.0,
        **kwargs
    )

    if not response.is_success:

        try:
            detalle = response.json()

        except ValueError:

            detalle = response.text[:2000]

        raise RuntimeError(
            f"Supabase respondió HTTP "
            f"{response.status_code}: {detalle}"
        )

    if not response.content:

        return []

    try:
        datos = response.json()

    except ValueError:

        return []

    if isinstance(datos, list):

        return datos

    if isinstance(datos, dict):

        return [datos]

    return []


# ============================================================
# SUBIR ARCHIVO A SUPABASE STORAGE
# ============================================================

def subir_archivo_supabase(
    bucket: str,
    path: str,
    contenido: bytes,
    content_type: str
):

    if not SUPABASE_URL:

        raise RuntimeError(
            "Falta configurar SUPABASE_URL."
        )

    if not SUPABASE_WRITE_KEY:

        raise RuntimeError(
            "Falta configurar "
            "SUPABASE_SERVICE_ROLE_KEY "
            "o SUPABASE_SECRET_KEY."
        )

    ruta = "/".join(
        quote_segmento(parte)
        for parte in path.split("/")
        if parte
    )

    bucket_url = quote_segmento(bucket)

    headers = encabezados_supabase_admin()

    headers["Content-Type"] = content_type
    headers["Cache-Control"] = "3600"
    headers["x-upsert"] = "false"

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{bucket_url}/{ruta}"
    )

    response = httpx.post(
        url,
        headers=headers,
        content=contenido,
        timeout=httpx.Timeout(
            connect=30.0,
            read=300.0,
            write=300.0,
            pool=30.0
        )
    )

    if not response.is_success:

        try:
            detalle = response.json()

        except ValueError:

            detalle = response.text[:2000]

        raise RuntimeError(
            "Supabase Storage respondió "
            f"HTTP {response.status_code}: "
            f"{detalle}"
        )

    return response


# ============================================================
# CODIFICAR RUTAS DE STORAGE
# ============================================================

def quote_segmento(valor: str) -> str:

    from urllib.parse import quote

    return quote(
        valor,
        safe=""
    )


# ============================================================
# OBTENER URL PÚBLICA
# ============================================================

def obtener_url_publica(
    cliente_admin,
    bucket: str,
    path: str
):

    resultado = (
        cliente_admin
        .storage
        .from_(bucket)
        .get_public_url(path)
    )

    if isinstance(
        resultado,
        str
    ):

        return resultado

    if isinstance(
        resultado,
        dict
    ):

        return (
            resultado.get("publicUrl")
            or resultado.get("public_url")
            or ""
        )

    return ""


# ============================================================
# UUID DE PUBLICACIÓN
# ============================================================

def uuid_publicacion_valido(
    publicacion_id
):

    try:

        return str(
            uuid.UUID(
                str(publicacion_id)
            )
        )

    except (
        AttributeError,
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# AUTENTICACIÓN ADMINISTRATIVA
# ============================================================

def requiere_admin(funcion):

    @wraps(funcion)
    def validar_admin(
        *args,
        **kwargs
    ):

        if not ADMIN_PASSWORD:

            return respuesta_error(
                "El panel requiere configurar "
                "ADMIN_PASSWORD.",
                503
            )

        if supabase_admin is None:

            return respuesta_error(
                SUPABASE_CONFIG_ERROR
                or (
                    "Configura una clave "
                    "Supabase de escritura."
                ),
                503
            )

        clave = request.headers.get(
            "X-Admin-Password",
            ""
        )

        if not isinstance(
            clave,
            str
        ):

            return respuesta_error(
                "Acceso administrativo "
                "no autorizado.",
                401
            )

        if not hmac.compare_digest(
            clave,
            ADMIN_PASSWORD
        ):

            return respuesta_error(
                "Acceso administrativo "
                "no autorizado.",
                401
            )

        return funcion(
            *args,
            **kwargs
        )

    return validar_admin


# ============================================================
# ARCHIVO DEMASIADO GRANDE
# ============================================================

@app.errorhandler(
    RequestEntityTooLarge
)
def archivo_demasiado_grande(
    _error
):

    return respuesta_error(
        "El archivo supera el límite "
        "de 100 MB.",
        413
    )


# ============================================================
# INICIO
# ============================================================

@app.route("/")
def inicio():

    return send_from_directory(
        app.root_path,
        "index.html"
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@app.route("/admin.html")
def panel_admin():

    return send_from_directory(
        app.root_path,
        "admin.html"
    )


# ============================================================
# ASSETS
# ============================================================

@app.route(
    "/assets/<path:filename>"
)
def servir_asset(filename):

    if filename not in PUBLIC_ASSETS:

        return respuesta_error(
            "Recurso no encontrado.",
            404
        )

    return send_from_directory(
        app.root_path,
        filename
    )


# ============================================================
# CONFIGURACIÓN PÚBLICA
# ============================================================

@app.route(
    "/api/public-config"
)
def configuracion_publica():

    return jsonify({
        "success": True,
        "realtimeEnabled": bool(
            SUPABASE_URL
            and SUPABASE_ANON_KEY
        ),
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": (
            SUPABASE_ANON_KEY
        )
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health")
def health():

    return jsonify({
        "success": True,
        "status": "online",
        "supabaseConfigured": bool(
            SUPABASE_URL
            and SUPABASE_ANON_KEY
        ),
        "adminConfigured": bool(
            ADMIN_PASSWORD
        ),
        "storageConfigured": bool(
            SUPABASE_STORAGE_BUCKET
        ),
        "maxUploadMB": (
            MAX_UPLOAD_BYTES
            // (1024 * 1024)
        ),
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    })


# ============================================================
# VERIFICAR ADMIN
# ============================================================

@app.route(
    "/api/admin/verify",
    methods=["POST"]
)
def verificar_admin():

    if not ADMIN_PASSWORD:

        return respuesta_error(
            "El panel requiere configurar "
            "ADMIN_PASSWORD.",
            503
        )

    datos = (
        request.get_json(
            silent=True
        )
        or {}
    )

    clave = datos.get(
        "password",
        ""
    )

    if not isinstance(
        clave,
        str
    ):

        return respuesta_error(
            "Contraseña incorrecta.",
            401
        )

    if not hmac.compare_digest(
        clave,
        ADMIN_PASSWORD
    ):

        return respuesta_error(
            "Contraseña incorrecta.",
            401
        )

    return jsonify({
        "success": True
    })


# ============================================================
# SECCIONES EDITORIALES
# ============================================================

@app.route(
    "/api/secciones",
    methods=["GET"]
)
def obtener_contenido_secciones():

    if supabase is None:

        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Supabase no está configurado.",
            503
        )

    try:

        filas = (
            supabase
            .table(
                "contenido_secciones"
            )
            .select(
                "seccion,contenido,updated_at"
            )
            .in_(
                "seccion",
                sorted(
                    SECCIONES_EDITORIALES
                )
            )
            .execute()
            .data
        )

        contenido = {
            seccion: None
            for seccion
            in SECCIONES_EDITORIALES
        }

        for fila in filas:

        from typing import Optional

def get_upper(text: Optional[str]) -> str:
    if text is not None:
        return text.upper()

    return ""
                contenido[
                    seccion
                ] = (
                    fila.get(
                        "contenido"
                    )
                    or ""
                )

        return jsonify({
            "success": True,
            "secciones": contenido
        })

    except Exception as error:

        app.logger.exception(
            "No se pudo cargar "
            "el contenido editorial."
        )

        return respuesta_error(
            str(error),
            500
        )


# ============================================================
# ACTUALIZAR SECCIÓN
# ============================================================

@app.route(
    "/api/secciones/<seccion>",
    methods=["PUT"]
)
@requiere_admin
def actualizar_contenido_seccion(
    seccion
):

    if (
        seccion
        not in SECCIONES_EDITORIALES
    ):

        return respuesta_error(
            "Sección editorial no válida.",
            404
        )

    datos = (
        request.get_json(
            silent=True
        )
        or {}
    )

    contenido = datos.get(
        "contenido"
    )

    if not isinstance(
        contenido,
        str
    ):

        return respuesta_error(
            "El contenido debe ser texto.",
            400
        )

    if len(contenido) > 100000:

        return respuesta_error(
            "El texto supera el límite "
            "de 100 000 caracteres.",
            413
        )

    actualizado = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    fila = {
        "seccion": seccion,
        "contenido": contenido,
        "updated_at": actualizado
    }

    try:

        guardada = None

        if (
            SUPABASE_WRITE_KEY
            and SUPABASE_WRITE_KEY.startswith(
                "sb_secret_"
            )
        ):

            filas = solicitar_supabase_admin(
                "POST",
                "contenido_secciones",
                params={
                    "on_conflict": "seccion"
                },
                json=fila,
                prefer=(
                    "resolution=merge-duplicates,"
                    "return=representation"
                )
            )

            if filas:

                guardada = filas[0]

        else:

            if supabase_admin is None:

                return respuesta_error(
                    "Supabase administrativo "
                    "no está configurado.",
                    503
                )

            filas = (
                supabase_admin
                .table(
                    "contenido_secciones"
                )
                .upsert(
                    fila,
                    on_conflict="seccion"
                )
                .execute()
                .data
            )

            if filas:

                guardada = filas[0]

        if not guardada:

            guardada = fila

        return jsonify({
            "success": True,
            "seccion": seccion,
            "contenido": guardada.get(
                "contenido",
                contenido
            ),
            "updated_at": guardada.get(
                "updated_at",
                actualizado
            )
        })

    except Exception as error:

        app.logger.exception(
            "No se pudo guardar "
            "el contenido editorial."
        )

        return respuesta_error(
            str(error),
            500
        )


# ============================================================
# PUBLICACIONES - GET
# ============================================================

@app.route(
    "/api/publicaciones",
    methods=["GET"]
)
def obtener_publicaciones():

    if supabase is None:

        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Supabase no está configurado.",
            503
        )

    seccion = request.args.get(
        "seccion"
    )

    if (
        seccion
        and seccion not in {
            "inicio",
            "fotos",
            "videos"
        }
    ):

        return respuesta_error(
            "Sección no válida.",
            400
        )

    try:

        consulta = (
            supabase
            .table(
                "publicaciones"
            )
            .select("*")
        )

        if seccion:

            consulta = consulta.eq(
                "seccion",
                seccion
            )

        publicaciones = (
            consulta
            .order(
                "fecha",
                desc=True
            )
            .execute()
            .data
        )

        return jsonify({
            "success": True,
            "publicaciones": (
                publicaciones
            )
        })

    except Exception as error:

        app.logger.exception(
            "No se pudieron consultar "
            "las publicaciones."
        )

        return respuesta_error(
            str(error),
            500
        )


# ============================================================
# COMENTARIOS - GET
# ============================================================

@app.route(
    "/api/publicaciones/"
    "<publicacion_id>/comentarios",
    methods=["GET"]
)
def obtener_comentarios(
    publicacion_id
):

    if supabase is None:

        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Supabase no está configurado.",
            503
        )

    publicacion_uuid = (
        uuid_publicacion_valido(
            publicacion_id
        )
    )

    if publicacion_uuid is None:

        return respuesta_error(
            "Publicación no válida.",
            400
        )

    try:
        comentarios = (
            supabase
            .table("comentarios")
            .select("*")
            .eq("publicacion_id", publicacion_uuid)
            .order("created_at", desc=False)
            .execute()
            .data
        )

        return jsonify({
            "success": True,
            "comentarios": comentarios or []
        })

    except Exception as error:
        app.logger.exception(
            "No se pudieron consultar los comentarios."
        )
        return respuesta_error(str(error), 500)


# ============================================================
# MANEJADORES GENERALES DE ERROR
# ============================================================

@app.errorhandler(404)
def recurso_no_encontrado(_error):
    return respuesta_error("Recurso no encontrado.", 404)


@app.errorhandler(405)
def metodo_no_permitido(_error):
    return respuesta_error("Método no permitido.", 405)


@app.errorhandler(500)
def error_interno(_error):
    return respuesta_error("Error interno del servidor.", 500)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False
    )
