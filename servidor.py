import hmac
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Optional, Dict, List, Union, Tuple, Set, cast

import httpx
from flask import Flask, jsonify, request, send_from_directory, Response
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

SECCIONES_EDITORIALES: Set[str] = {
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
# FORMATOS MULTIMEDIA Y DOCUMENTOS PERMITIDOS
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

    ".pdf": ("application/pdf", "document"),
    ".doc": ("application/msword", "document"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document"),
}


# ============================================================
# INICIALIZACIÓN DE SUPABASE
# ============================================================

SUPABASE_CONFIG_ERROR: Optional[str] = None

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
) -> Tuple[Response, int]:

    return jsonify({
        "success": False,
        "error": str(mensaje)
    }), estado


# ============================================================
# HEADERS PARA SUPABASE
# ============================================================

def encabezados_supabase_admin() -> Dict[str, str]:

    if not SUPABASE_WRITE_KEY:

        raise RuntimeError(
            "Falta configurar "
            "SUPABASE_SERVICE_ROLE_KEY "
            "o SUPABASE_SECRET_KEY."
        )

    headers = {
        "apikey": SUPABASE_WRITE_KEY
    }

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
    **kwargs: Any
) -> List[Any]:

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
) -> httpx.Response:

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
    cliente_admin: Any,
    bucket: str,
    path: str
) -> str:

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
    publicacion_id: Any
) -> Optional[str]:

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

def requiere_admin(funcion: Any) -> Any:

    @wraps(funcion)
    def validar_admin(
        *args: Any,
        **kwargs: Any
    ) -> Any:

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
    _error: Any
) -> Tuple[Response, int]:

    return respuesta_error(
        "El archivo supera el límite "
        "de 100 MB.",
        413
    )


# ============================================================
# INICIO
# ============================================================

@app.route("/")
def inicio() -> Any:

    return send_from_directory(
        app.root_path,
        "index.html"
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@app.route("/admin.html")
def panel_admin() -> Any:

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
def servir_asset(filename: str) -> Any:

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
def configuracion_publica() -> Any:

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
def health() -> Any:

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
def verificar_admin() -> Any:

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
# SECCIONES EDITORIALES (VIDA / OBRA) - TEXTO Y DOCUMENTOS
# ============================================================

@app.route(
    "/api/secciones",
    methods=["GET"]
)
def obtener_contenido_secciones() -> Any:

    if supabase is None:

        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Supabase no está configurado.",
            503
        )

    try:

        secciones_lista: List[str] = sorted(list(SECCIONES_EDITORIALES))

        respuesta_query = (
            supabase
            .table(
                "contenido_secciones"
            )
            .select(
                "seccion,contenido,archivo_url,updated_at"
            )
            .in_(
                "seccion",
                cast(Any, secciones_lista)
            )
            .execute()
        )

        filas = cast(List[Any], respuesta_query.data if respuesta_query and respuesta_query.data else [])

        contenido: Dict[str, Dict[str, Any]] = {
            seccion: {"contenido": "", "archivo_url": None}
            for seccion
            in SECCIONES_EDITORIALES
        }

        for fila in filas:
            if isinstance(fila, dict):
                seccion_val = fila.get("seccion")
                if seccion_val in SECCIONES_EDITORIALES:
                    contenido[seccion_val] = {
                        "contenido": fila.get("contenido") or "",
                        "archivo_url": fila.get("archivo_url")
                    }

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
# ACTUALIZAR SECCIÓN (VIDA / OBRA)
# ============================================================

@app.route(
    "/api/secciones/<seccion>",
    methods=["PUT"]
)
@requiere_admin
def actualizar_contenido_seccion(
    seccion: str
) -> Any:

    if (
        seccion
        not in SECCIONES_EDITORIALES
    ):

        return respuesta_error(
            "Sección editorial no válida.",
            404
        )

    contenido = request.form.get("contenido", "")

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

    archivo_url: Optional[str] = None
    archivo = request.files.get("archivo")

    if archivo and archivo.filename:
        nombre_original = secure_filename(archivo.filename)
        extension = Path(nombre_original).suffix.lower()

        if extension not in ALLOWED_MEDIA or ALLOWED_MEDIA[extension][1] not in ("document", "image"):
            return respuesta_error(
                "Formato de archivo no permitido para secciones editoriales.",
                400
            )

        content_type, _ = ALLOWED_MEDIA[extension]
        bytes_archivo = archivo.read()
        sufijo_unico = uuid.uuid4().hex[:8]
        ruta_storage = f"secciones/{seccion}/{sufijo_unico}_{nombre_original}"

        try:
            subir_archivo_supabase(
                SUPABASE_STORAGE_BUCKET,
                ruta_storage,
                bytes_archivo,
                content_type
            )
            if supabase_admin:
                archivo_url = obtener_url_publica(
                    supabase_admin,
                    SUPABASE_STORAGE_BUCKET,
                    ruta_storage
                )
        except Exception as err:
            return respuesta_error(
                f"Error al subir el archivo: {err}",
                500
            )

    actualizado = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    fila: Dict[str, Any] = {
        "seccion": seccion,
        "contenido": contenido,
        "updated_at": actualizado
    }

    if archivo_url:
        fila["archivo_url"] = archivo_url

    try:

        guardada: Optional[Dict[str, Any]] = None

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

            if filas and isinstance(filas, list):

                guardada = cast(Dict[str, Any], filas[0])

        else:

            if supabase_admin is None:

                return respuesta_error(
                    "Supabase administrativo "
                    "no está configurado.",
                    503
                )

            res_upsert = (
                supabase_admin
                .table(
                    "contenido_secciones"
                )
                .upsert(
                    fila,
                    on_conflict="seccion"
                )
                .execute()
            )

            filas = cast(List[Any], res_upsert.data if res_upsert and res_upsert.data else [])

            if filas and isinstance(filas, list):

                guardada = cast(Dict[str, Any], filas[0])

        if not guardada:

            guardada = fila

        return jsonify({
            "success": True,
            "seccion": seccion,
            "contenido": guardada.get(
                "contenido",
                contenido
            ),
            "archivo_url": guardada.get("archivo_url"),
            "updated_at": guardada.get(
                "updated_at",
                actualizado
            )
        })

    except Exception as error:

        app.logger.exception(
            "No se pudo guardar el contenido editorial."
        )

        msg_error = str(error)
        return respuesta_error(msg_error, 500)


# ============================================================
# PUBLICACIONES (INICIO / PORTAL, FOTOS, VIDEOS)
# ========