import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Optional, Dict, List, Union, Tuple, Set, cast
from urllib.parse import unquote, urlsplit, urlunsplit

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

def normalizar_supabase_url(valor: str) -> str:
    """Devuelve la URL raíz del proyecto, aunque Render incluya /rest/v1."""
    valor = (valor or "").strip().rstrip("/")
    if not valor:
        return ""

    partes = urlsplit(valor)
    ruta = partes.path.rstrip("/")
    sufijo_rest = "/rest/v1"
    if ruta.endswith(sufijo_rest):
        ruta = ruta[:-len(sufijo_rest)]

    return urlunsplit(partes._replace(path=ruta)).rstrip("/")


SUPABASE_URL = normalizar_supabase_url(
    os.environ.get("SUPABASE_URL") or ""
)

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

# Secciones fijas editoriales de la página
SECCIONES_EDITORIALES: Set[str] = {
    "vida",
    "obra"
}

SECCIONES_PUBLICACIONES: Set[str] = {
    "inicio",
    "fotos",
    "videos"
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
    # Imágenes
    ".gif": ("image/gif", "image"),
    ".jpeg": ("image/jpeg", "image"),
    ".jpg": ("image/jpeg", "image"),
    ".png": ("image/png", "image"),
    ".webp": ("image/webp", "image"),

    # Videos
    ".m4v": ("video/x-m4v", "video"),
    ".mov": ("video/quicktime", "video"),
    ".mp4": ("video/mp4", "video"),
    ".webm": ("video/webm", "video"),

    # Documentos (para la sección de obras: PDF, Word)
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


def eliminar_archivo_supabase(
    bucket: str,
    path: str
) -> None:

    if not path:
        return

    bucket_url = quote_segmento(bucket)
    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{bucket_url}"
    )
    headers = encabezados_supabase_admin()
    headers["Content-Type"] = "application/json"
    response = httpx.request(
        "DELETE",
        url,
        headers=headers,
        json={"prefixes": [path]},
        timeout=60.0
    )

    if response.status_code == 404:
        return

    if not response.is_success:
        try:
            detalle = response.json()
        except ValueError:
            detalle = response.text[:1000]
        raise RuntimeError(
            f"Supabase Storage respondió HTTP {response.status_code}: {detalle}"
        )


def ruta_storage_desde_url(
    url: Optional[str],
    bucket: str
) -> Optional[str]:

    if not url or not SUPABASE_URL:
        return None

    partes = urlsplit(url)
    proyecto = urlsplit(SUPABASE_URL)
    prefijo = (
        f"/storage/v1/object/public/"
        f"{quote_segmento(bucket)}/"
    )

    if (
        partes.netloc.lower() != proyecto.netloc.lower()
        or not partes.path.startswith(prefijo)
    ):
        return None

    path = unquote(partes.path[len(prefijo):]).strip("/")
    return path or None


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


@app.route("/robots.txt")
def robots_txt() -> Response:
    contenido = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Sitemap: https://alfredomaneiro.org.ve/sitemap.xml\n"
    )
    respuesta = Response(contenido, mimetype="text/plain")
    respuesta.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    return respuesta


@app.route("/sitemap.xml")
def sitemap_xml() -> Response:
    contenido = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://alfredomaneiro.org.ve/</loc></url>"
        "</urlset>\n"
    )
    return Response(contenido, mimetype="application/xml")


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
# PUBLICACIONES GENERALES Y GALERÍAS
# ============================================================

@app.route("/api/publicaciones", methods=["GET"])
def obtener_publicaciones() -> Any:

    if supabase is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR or "Supabase no está configurado.",
            503
        )

    seccion = request.args.get("seccion", "").strip().lower()
    if seccion and seccion not in SECCIONES_PUBLICACIONES:
        return respuesta_error("Sección de publicaciones no válida.", 400)

    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return respuesta_error("El desplazamiento solicitado no es válido.", 400)
    if offset < 0 or offset > 1000000:
        return respuesta_error("El desplazamiento solicitado está fuera de rango.", 400)

    try:
        consulta = (
            supabase
            .table("publicaciones")
            .select("id,titulo,texto,mediaUrl,mediaType,mediaPath,seccion,fecha")
            .order("fecha", desc=True)
            .range(offset, offset + 99)
        )
        if seccion:
            consulta = consulta.eq("seccion", seccion)

        respuesta_query = consulta.execute()
        filas = cast(List[Any], respuesta_query.data or [])
        return jsonify({"success": True, "publicaciones": filas})

    except Exception as error:
        app.logger.exception("No se pudieron cargar las publicaciones.")
        return respuesta_error(str(error), 500)


@app.route("/api/publicaciones", methods=["POST"])
@requiere_admin
def crear_publicacion() -> Any:

    if supabase_admin is None:
        return respuesta_error("Supabase administrativo no está configurado.", 503)

    seccion = request.form.get("seccion", "").strip().lower()
    if seccion not in SECCIONES_PUBLICACIONES:
        return respuesta_error("Sección de publicaciones no válida.", 400)

    titulo = request.form.get("titulo", "").strip()
    texto = request.form.get("texto", "").strip()
    archivo = request.files.get("file")

    if len(titulo) > 300 or len(texto) > 100000:
        return respuesta_error("El título o el texto supera el límite permitido.", 400)
    if not titulo and not texto and not (archivo and archivo.filename):
        return respuesta_error("Indica un título, texto o archivo.", 400)
    if seccion in {"fotos", "videos"} and not (archivo and archivo.filename):
        return respuesta_error("Selecciona un archivo para la galería.", 400)

    media_url: Optional[str] = None
    media_type: Optional[str] = None
    media_path: Optional[str] = None

    if archivo and archivo.filename:
        nombre_original = secure_filename(archivo.filename)
        extension = Path(nombre_original).suffix.lower()
        metadata = ALLOWED_MEDIA.get(extension)
        if not metadata:
            return respuesta_error("Formato de archivo no permitido.", 400)

        content_type, tipo = metadata
        if tipo not in {"image", "video"}:
            return respuesta_error("Solo se permiten imágenes o videos en estas publicaciones.", 400)
        if seccion == "fotos" and tipo != "image":
            return respuesta_error("La sección Fotos solo admite imágenes.", 400)
        if seccion == "videos" and tipo != "video":
            return respuesta_error("La sección Videos solo admite videos.", 400)

        media_path = f"publicaciones/{seccion}/{uuid.uuid4().hex}_{nombre_original}"
        try:
            contenido_archivo = archivo.read()
            subir_archivo_supabase(
                SUPABASE_STORAGE_BUCKET,
                media_path,
                contenido_archivo,
                content_type
            )
            media_url = obtener_url_publica(
                supabase_admin,
                SUPABASE_STORAGE_BUCKET,
                media_path
            )
            media_type = tipo
        except Exception as error:
            app.logger.exception("No se pudo subir el medio de la publicación.")
            return respuesta_error(f"No se pudo subir el archivo: {error}", 500)

    fila: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "texto": texto,
        "mediaUrl": media_url,
        "mediaType": media_type,
        "mediaPath": media_path,
        "seccion": seccion,
        "fecha": datetime.now(timezone.utc).isoformat()
    }

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST",
                "publicaciones",
                json=fila,
                prefer="return=representation"
            )
            publicacion = filas[0] if filas else fila
        else:
            respuesta_insert = (
                supabase_admin
                .table("publicaciones")
                .insert(fila)
                .execute()
            )
            filas = cast(List[Any], respuesta_insert.data or [])
            publicacion = filas[0] if filas else fila

        return jsonify({"success": True, "publicacion": publicacion})

    except Exception as error:
        app.logger.exception("No se pudo guardar la publicación.")
        return respuesta_error(str(error), 500)


@app.route("/api/publicaciones/<publicacion_id>", methods=["DELETE"])
@requiere_admin
def eliminar_publicacion(publicacion_id: str) -> Any:

    if supabase_admin is None:
        return respuesta_error("Supabase administrativo no está configurado.", 503)

    seccion_esperada = request.args.get("seccion", "inicio").strip().lower()
    if seccion_esperada not in SECCIONES_PUBLICACIONES:
        return respuesta_error("Sección de publicaciones no válida.", 400)

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            publicaciones = solicitar_supabase_admin(
                "GET",
                "publicaciones",
                params={
                    "id": f"eq.{publicacion_id}",
                    "seccion": f"eq.{seccion_esperada}",
                    "select": "id,seccion,mediaPath,mediaUrl",
                    "limit": "1"
                }
            )
        else:
            respuesta_publicacion = (
                supabase_admin
                .table("publicaciones")
                .select("id,seccion,mediaPath,mediaUrl")
                .eq("id", publicacion_id)
                .eq("seccion", seccion_esperada)
                .limit(1)
                .execute()
            )
            publicaciones = cast(List[Any], respuesta_publicacion.data or [])

        if not publicaciones or not isinstance(publicaciones[0], dict):
            return respuesta_error("No se encontró la publicación.", 404)

        publicacion = cast(Dict[str, Any], publicaciones[0])
        if publicacion.get("seccion") != seccion_esperada:
            return respuesta_error(
                "La publicación no pertenece a la sección indicada.",
                409
            )

        media_path = publicacion.get("mediaPath")
        if media_path is not None and not isinstance(media_path, str):
            return respuesta_error("La ruta del archivo guardado no es válida.", 409)
        media_path = media_path.strip() if isinstance(media_path, str) else ""
        if not media_path and isinstance(publicacion.get("mediaUrl"), str):
            media_path = ruta_storage_desde_url(
                publicacion.get("mediaUrl"),
                SUPABASE_STORAGE_BUCKET
            ) or ""

        media_eliminado: Optional[bool] = None
        if media_path:
            partes_media = media_path.split("/")
            partes_validas = (
                all(
                    parte and parte not in {".", ".."}
                    for parte in partes_media
                )
                and "\\" not in media_path
            )
            ruta_actual = (
                len(partes_media) == 3
                and partes_media[0] == "publicaciones"
                and partes_media[1] == seccion_esperada
            )
            # Before per-section folders were introduced, uploaded media was
            # stored directly under publicaciones/. The row's section and ID
            # were already verified above, so allow only a single filename
            # component for this legacy layout.
            ruta_heredada = (
                len(partes_media) == 2
                and partes_media[0] == "publicaciones"
            )
            if not partes_validas or not (ruta_actual or ruta_heredada):
                return respuesta_error(
                    "El archivo no pertenece a la sección de esta publicación; no se eliminó nada.",
                    409
                )
            eliminar_archivo_supabase(
                SUPABASE_STORAGE_BUCKET,
                media_path
            )
            media_eliminado = True

        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "DELETE",
                "publicaciones",
                params={
                    "id": f"eq.{publicacion_id}",
                    "seccion": f"eq.{seccion_esperada}"
                },
                prefer="return=representation"
            )
        else:
            respuesta_delete = (
                supabase_admin
                .table("publicaciones")
                .delete()
                .eq("id", publicacion_id)
                .eq("seccion", seccion_esperada)
                .execute()
            )
            filas = cast(List[Any], respuesta_delete.data or [])

        if not filas:
            return respuesta_error("No se encontró la publicación.", 404)

        return jsonify({
            "success": True,
            "media_eliminado": media_eliminado
        })

    except Exception as error:
        app.logger.exception("No se pudo eliminar la publicación.")
        return respuesta_error(str(error), 500)


# ============================================================
# COMENTARIOS DE PUBLICACIONES
# ============================================================

@app.route(
    "/api/publicaciones/<publicacion_id>/comentarios",
    methods=["GET"]
)
def obtener_comentarios(publicacion_id: str) -> Any:

    if supabase is None:
        return respuesta_error(SUPABASE_CONFIG_ERROR or "Supabase no está configurado.", 503)

    try:
        respuesta_query = (
            supabase
            .table("comentarios")
            .select("id,publicacion_id,nombre,texto,created_at")
            .eq("publicacion_id", publicacion_id)
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )
        comentarios = cast(List[Any], respuesta_query.data or [])
        return jsonify({"success": True, "comentarios": comentarios})

    except Exception as error:
        app.logger.exception("No se pudieron cargar los comentarios.")
        return respuesta_error(str(error), 500)


@app.route(
    "/api/publicaciones/<publicacion_id>/comentarios",
    methods=["POST"]
)
def crear_comentario(publicacion_id: str) -> Any:

    if supabase is None or supabase_admin is None:
        return respuesta_error("El servicio de comentarios no está configurado.", 503)

    datos = request.get_json(silent=True) or {}
    texto = datos.get("texto", "")
    if not isinstance(texto, str):
        return respuesta_error("El comentario debe ser texto.", 400)
    texto = texto.strip()
    if not texto or len(texto) > 1000:
        return respuesta_error("Escribe un comentario de hasta 1000 caracteres.", 400)

    try:
        publicacion = (
            supabase
            .table("publicaciones")
            .select("id")
            .eq("id", publicacion_id)
            .limit(1)
            .execute()
        )
        if not (publicacion.data or []):
            return respuesta_error("No se encontró la publicación.", 404)

        fila = {
            "publicacion_id": publicacion_id,
            "nombre": "Visitante",
            "texto": texto
        }
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST", "comentarios", json=fila, prefer="return=representation"
            )
            comentario = filas[0] if filas else fila
        else:
            respuesta_insert = supabase_admin.table("comentarios").insert(fila).execute()
            filas = cast(List[Any], respuesta_insert.data or [])
            comentario = filas[0] if filas else fila

        return jsonify({"success": True, "comentario": comentario})

    except Exception as error:
        app.logger.exception("No se pudo guardar el comentario.")
        return respuesta_error(str(error), 500)


# ============================================================
# SUSCRIPCIONES
# ============================================================

@app.route("/api/suscripciones/count", methods=["GET"])
def contar_suscriptores() -> Any:

    if supabase_admin is None:
        return respuesta_error("El servicio de suscripciones no está configurado.", 503)

    try:
        respuesta_query = (
            supabase_admin
            .table("suscriptores")
            .select("id", count="exact", head=True)
            .execute()
        )
        return jsonify({"success": True, "count": int(respuesta_query.count or 0)})

    except Exception as error:
        app.logger.exception("No se pudo contar a los suscriptores.")
        return respuesta_error(str(error), 500)


@app.route("/api/suscripciones", methods=["POST"])
def crear_suscripcion() -> Any:

    if supabase_admin is None:
        return respuesta_error("El servicio de suscripciones no está configurado.", 503)

    datos = request.get_json(silent=True) or {}
    email = datos.get("email", "")
    if not isinstance(email, str):
        return respuesta_error("El correo electrónico no es válido.", 400)
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return respuesta_error("El correo electrónico no es válido.", 400)

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST",
                "suscriptores",
                params={"on_conflict": "email"},
                json={"email": email},
                prefer="resolution=ignore-duplicates,return=representation"
            )
        else:
            respuesta_insert = (
                supabase_admin
                .table("suscriptores")
                .upsert({"email": email}, on_conflict="email", ignore_duplicates=True)
                .execute()
            )
            filas = cast(List[Any], respuesta_insert.data or [])

        return jsonify({"success": True, "alreadySubscribed": not bool(filas)})

    except Exception as error:
        app.logger.exception("No se pudo completar la suscripción.")
        return respuesta_error(str(error), 500)


# ============================================================
# DATOS PÚBLICOS DE CONTACTO
# ============================================================

CONTACTO_VACIO = {
    "whatsapp": "",
    "email": "",
    "messenger_url": "",
    "tiktok_handle": ""
}


@app.route("/api/contacto-publico", methods=["GET"])
def obtener_contacto_publico() -> Any:

    if supabase is None:
        return respuesta_error(SUPABASE_CONFIG_ERROR or "Supabase no está configurado.", 503)

    try:
        respuesta_query = (
            supabase
            .table("contacto_publico")
            .select("whatsapp,email,messenger_url,tiktok_handle")
            .eq("id", 1)
            .limit(1)
            .execute()
        )
        filas = cast(List[Any], respuesta_query.data or [])
        contacto = dict(CONTACTO_VACIO)
        if filas and isinstance(filas[0], dict):
            contacto.update({campo: filas[0].get(campo) or "" for campo in CONTACTO_VACIO})
        return jsonify({"success": True, "contacto": contacto})

    except Exception as error:
        app.logger.exception("No se pudieron cargar los canales de contacto.")
        return respuesta_error(str(error), 500)


@app.route("/api/contacto-publico", methods=["PUT"])
@requiere_admin
def actualizar_contacto_publico() -> Any:

    if supabase_admin is None:
        return respuesta_error("Supabase administrativo no está configurado.", 503)

    datos = request.get_json(silent=True) or {}
    contacto: Dict[str, str] = {}
    for campo in CONTACTO_VACIO:
        valor = datos.get(campo, "")
        if not isinstance(valor, str):
            return respuesta_error("Los campos de contacto deben ser texto.", 400)
        contacto[campo] = valor.strip()

    whatsapp = contacto["whatsapp"]
    if whatsapp and (
        not re.fullmatch(r"[+0-9().\-\s]{7,32}", whatsapp)
        or len(re.sub(r"\D", "", whatsapp)) < 7
    ):
        return respuesta_error("El número de WhatsApp no es válido.", 400)

    email = contacto["email"]
    if email and (
        len(email) > 254
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
    ):
        return respuesta_error("El correo electrónico no es válido.", 400)

    messenger = contacto["messenger_url"]
    if messenger:
        partes = urlsplit(messenger)
        host = (partes.hostname or "").lower()
        if (
            partes.scheme != "https"
            or not host
            or not (host == "m.me" or host == "messenger.com" or host.endswith(".messenger.com") or host == "facebook.com" or host.endswith(".facebook.com"))
            or len(messenger) > 2048
        ):
            return respuesta_error("El enlace de Messenger debe ser una URL HTTPS de Facebook/Messenger.", 400)

    tiktok = contacto["tiktok_handle"]
    if tiktok and not re.fullmatch(r"@?[A-Za-z0-9._]{2,24}", tiktok):
        return respuesta_error("Indica el usuario de TikTok (por ejemplo, @usuario).", 400)

    fila: Dict[str, Any] = {
        "id": 1,
        **contacto,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST",
                "contacto_publico",
                params={"on_conflict": "id"},
                json=fila,
                prefer="resolution=merge-duplicates,return=representation"
            )
            guardado = filas[0] if filas else fila
        else:
            respuesta_upsert = (
                supabase_admin
                .table("contacto_publico")
                .upsert(fila, on_conflict="id")
                .execute()
            )
            filas = cast(List[Any], respuesta_upsert.data or [])
            guardado = filas[0] if filas else fila

        return jsonify({"success": True, "contacto": guardado})

    except Exception as error:
        app.logger.exception("No se pudieron guardar los canales de contacto.")
        return respuesta_error(str(error), 500)


@app.route("/api/contacto-publico", methods=["DELETE"])
@requiere_admin
def eliminar_contacto_publico() -> Any:

    if supabase_admin is None:
        return respuesta_error("Supabase administrativo no está configurado.", 503)

    fila: Dict[str, Any] = {
        "id": 1,
        **CONTACTO_VACIO,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST",
                "contacto_publico",
                params={"on_conflict": "id"},
                json=fila,
                prefer="resolution=merge-duplicates,return=representation"
            )
            guardado = filas[0] if filas else fila
        else:
            respuesta_upsert = (
                supabase_admin
                .table("contacto_publico")
                .upsert(fila, on_conflict="id")
                .execute()
            )
            filas = cast(List[Any], respuesta_upsert.data or [])
            guardado = filas[0] if filas else fila

        return jsonify({"success": True, "contacto": guardado})

    except Exception as error:
        app.logger.exception("No se pudieron eliminar los canales de contacto.")
        return respuesta_error(str(error), 500)


# ============================================================
# SECCIONES EDITORIALES (VIDA / OBRA / INICIO) - TEXTO Y DOCUMENTOS
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

        contenido: Dict[str, str] = {
            seccion: ""
            for seccion
            in SECCIONES_EDITORIALES
        }
        archivos: Dict[str, Optional[str]] = {
            seccion: None
            for seccion
            in SECCIONES_EDITORIALES
        }

        for fila in filas:
            if isinstance(fila, dict):
                seccion_val = fila.get("seccion")
                if seccion_val in SECCIONES_EDITORIALES:
                    contenido[seccion_val] = fila.get("contenido") or ""
                    archivos[seccion_val] = fila.get("archivo_url")

        return jsonify({
            "success": True,
            "secciones": contenido,
            "archivos": archivos
        })

    except Exception as error:

        app.logger.exception(
            "No se pudo cargar el contenido editorial."
        )

        return respuesta_error(
            str(error),
            500
        )


# ============================================================
# ACTUALIZAR SECCIÓN (VIDA / OBRA / INICIO)
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

    datos_json = request.get_json(silent=True) or {}
    contenido = request.form.get(
        "contenido",
        datos_json.get("contenido", "")
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

    archivo_url: Optional[str] = None
    archivo = request.files.get("archivo")
    ruta_archivo_anterior: Optional[str] = None

    if archivo and archivo.filename:
        try:
            if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
                archivos_anteriores = solicitar_supabase_admin(
                    "GET",
                    "contenido_secciones",
                    params={
                        "seccion": f"eq.{seccion}",
                        "select": "archivo_url",
                        "limit": "1"
                    }
                )
            else:
                if supabase_admin is None:
                    return respuesta_error(
                        "Supabase administrativo no está configurado.",
                        503
                    )
                respuesta_anterior = (
                    supabase_admin
                    .table("contenido_secciones")
                    .select("archivo_url")
                    .eq("seccion", seccion)
                    .limit(1)
                    .execute()
                )
                archivos_anteriores = cast(
                    List[Any],
                    respuesta_anterior.data or []
                )

            if archivos_anteriores and isinstance(archivos_anteriores[0], dict):
                url_anterior = archivos_anteriores[0].get("archivo_url")
                if isinstance(url_anterior, str):
                    ruta_archivo_anterior = ruta_storage_desde_url(
                        url_anterior,
                        SUPABASE_STORAGE_BUCKET
                    )
                    if (
                        ruta_archivo_anterior
                        and not ruta_archivo_anterior.startswith(f"secciones/{seccion}/")
                    ):
                        ruta_archivo_anterior = None
        except Exception as error:
            app.logger.exception("No se pudo revisar el archivo previo de la sección.")
            return respuesta_error(str(error), 500)

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

        if ruta_archivo_anterior and ruta_archivo_anterior != ruta_storage:
            try:
                eliminar_archivo_supabase(
                    SUPABASE_STORAGE_BUCKET,
                    ruta_archivo_anterior
                )
            except Exception as error_storage:
                app.logger.warning(
                    "Se actualizó %s, pero no se pudo retirar el archivo previo: %s",
                    seccion,
                    error_storage
                )

        return jsonify({
            "success": True,
            "message": "Publicación hecha exitosamente en la base de datos",
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
        app.logger.exception("No se pudo guardar el contenido editorial.")
        return respuesta_error(str(error), 500)


@app.route(
    "/api/secciones/<seccion>",
    methods=["DELETE"]
)
@requiere_admin
def eliminar_contenido_seccion(seccion: str) -> Any:

    if seccion not in SECCIONES_EDITORIALES:
        return respuesta_error("Sección editorial no válida.", 404)

    if supabase_admin is None:
        return respuesta_error("Supabase administrativo no está configurado.", 503)

    try:
        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas_seccion = solicitar_supabase_admin(
                "GET",
                "contenido_secciones",
                params={
                    "seccion": f"eq.{seccion}",
                    "select": "seccion,archivo_url",
                    "limit": "1"
                }
            )
        else:
            respuesta_seccion = (
                supabase_admin
                .table("contenido_secciones")
                .select("seccion,archivo_url")
                .eq("seccion", seccion)
                .limit(1)
                .execute()
            )
            filas_seccion = cast(List[Any], respuesta_seccion.data or [])

        if not filas_seccion or not isinstance(filas_seccion[0], dict):
            return jsonify({
                "success": True,
                "seccion": seccion,
                "archivo_eliminado": False,
                "already_empty": True
            })

        fila_seccion = cast(Dict[str, Any], filas_seccion[0])
        archivo_url = fila_seccion.get("archivo_url")
        if archivo_url is not None and not isinstance(archivo_url, str):
            return respuesta_error("La URL del archivo guardado no es válida.", 409)
        archivo_path = ruta_storage_desde_url(
            archivo_url,
            SUPABASE_STORAGE_BUCKET
        )
        if archivo_path:
            prefijo_esperado = f"secciones/{seccion}/"
            if not archivo_path.startswith(prefijo_esperado):
                return respuesta_error(
                    "El archivo no pertenece a esta sección; no se eliminó nada.",
                    409
                )
            eliminar_archivo_supabase(
                SUPABASE_STORAGE_BUCKET,
                archivo_path
            )

        if SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas_eliminadas = solicitar_supabase_admin(
                "DELETE",
                "contenido_secciones",
                params={"seccion": f"eq.{seccion}"},
                prefer="return=representation"
            )
        else:
            respuesta_delete = (
                supabase_admin
                .table("contenido_secciones")
                .delete()
                .eq("seccion", seccion)
                .execute()
            )
            filas_eliminadas = cast(List[Any], respuesta_delete.data or [])

        if not filas_eliminadas:
            return jsonify({
                "success": True,
                "seccion": seccion,
                "archivo_eliminado": False,
                "already_empty": True
            })

        return jsonify({
            "success": True,
            "seccion": seccion,
            "archivo_eliminado": bool(archivo_path),
            "already_empty": False
        })

    except Exception as error:
        app.logger.exception("No se pudo eliminar el contenido editorial.")
        return respuesta_error(str(error), 500)
