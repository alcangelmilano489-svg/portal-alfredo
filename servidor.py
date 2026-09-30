import hmac
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from supabase import create_client
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_WRITE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
)
SUPABASE_READ_KEY = SUPABASE_ANON_KEY or SUPABASE_WRITE_KEY
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if (
    not SUPABASE_URL
    or not SUPABASE_READ_KEY
    or not ADMIN_PASSWORD
):
    raise RuntimeError(
        "SUPABASE_URL, SUPABASE_ANON_KEY or SUPABASE_KEY, and ADMIN_PASSWORD "
        "must be configured"
    )

SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "media")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
supabase = create_client(SUPABASE_URL, SUPABASE_READ_KEY)
supabase_admin = (
    create_client(SUPABASE_URL, SUPABASE_WRITE_KEY) if SUPABASE_WRITE_KEY else None
)

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


def respuesta_error(mensaje, estado):
    return jsonify({"success": False, "error": mensaje}), estado


@app.errorhandler(RequestEntityTooLarge)
def archivo_demasiado_grande(_error):
    return respuesta_error("El archivo supera el límite de 100 MB.", 413)


def requiere_admin(funcion):
    @wraps(funcion)
    def validar_admin(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return respuesta_error("El panel requiere configurar ADMIN_PASSWORD.", 503)
        if supabase_admin is None:
            return respuesta_error(
                "Configura SUPABASE_SERVICE_ROLE_KEY o SUPABASE_KEY con permisos de escritura.",
                503,
            )

        clave = request.headers.get("X-Admin-Password", "")
        if not hmac.compare_digest(clave, ADMIN_PASSWORD):
            return respuesta_error("Acceso administrativo no autorizado.", 401)

        return funcion(*args, **kwargs)

    return validar_admin


@app.route("/")
def inicio():
    return send_from_directory(app.root_path, "index.html")


@app.route("/admin")
@app.route("/admin.html")
def panel_admin():
    return send_from_directory(app.root_path, "admin.html")


@app.route("/api/public-config")
def configuracion_publica():
    return jsonify({
        "success": True,
        "realtimeEnabled": bool(SUPABASE_ANON_KEY),
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": SUPABASE_ANON_KEY,
    })


@app.route("/assets/<path:filename>")
def servir_asset(filename):
    if filename not in PUBLIC_ASSETS:
        return respuesta_error("Recurso no encontrado.", 404)
    return send_from_directory(app.root_path, filename)


@app.route("/api/admin/verify", methods=["POST"])
def verificar_admin():
    if not ADMIN_PASSWORD:
        return respuesta_error("El panel requiere configurar ADMIN_PASSWORD.", 503)

    datos = request.get_json(silent=True) or {}
    clave = datos.get("password", "")
    if not isinstance(clave, str) or not hmac.compare_digest(clave, ADMIN_PASSWORD):
        return respuesta_error("Contraseña incorrecta.", 401)
    return jsonify({"success": True})


@app.route("/api/publicaciones", methods=["GET"])
def obtener_publicaciones():
    seccion = request.args.get("seccion")
    if seccion and seccion not in {"inicio", "fotos", "videos"}:
        return respuesta_error("Sección no válida.", 400)

    try:
        consulta = supabase.table("publicaciones").select("*")
        if seccion:
            consulta = consulta.eq("seccion", seccion)
        publicaciones = consulta.order("fecha", desc=True).execute().data
        return jsonify({"success": True, "publicaciones": publicaciones})
    except Exception as error:
        app.logger.exception("No se pudieron consultar las publicaciones")
        return respuesta_error(str(error), 500)


@app.route("/api/publicaciones", methods=["POST"])
@requiere_admin
def crear_publicacion():
    cliente_admin = supabase_admin
    if cliente_admin is None:
        return respuesta_error(
            "Configura SUPABASE_SERVICE_ROLE_KEY o SUPABASE_KEY con permisos de escritura.",
            503,
        )

    titulo = request.form.get("titulo", "").strip()
    texto = request.form.get("texto", "").strip()
    seccion = request.form.get("seccion", "inicio")
    archivo = request.files.get("file")

    if seccion not in {"inicio", "fotos", "videos"}:
        return respuesta_error("Sección no válida.", 400)
    if not titulo and not texto and (archivo is None or not archivo.filename):
        return respuesta_error("Agrega texto, un título o un archivo.", 400)

    media_path = None
    media_url = None
    media_type = None

    try:
        if archivo and archivo.filename:
            nombre = secure_filename(archivo.filename)
            extension = Path(nombre).suffix.lower()
            tipo_archivo = ALLOWED_MEDIA.get(extension)
            if not nombre or tipo_archivo is None:
                return respuesta_error("Formato de archivo no permitido.", 400)

            content_type, media_type = tipo_archivo
            if seccion == "videos" and media_type != "video":
                return respuesta_error("La sección Videos solo acepta videos.", 400)
            if seccion == "fotos" and media_type != "image":
                return respuesta_error("La sección Fotos solo acepta imágenes.", 400)

            contenido = archivo.stream.read(MAX_UPLOAD_BYTES + 1)
            if not contenido:
                return respuesta_error("El archivo está vacío.", 400)
            if len(contenido) > MAX_UPLOAD_BYTES:
                return respuesta_error("El archivo supera el límite de 100 MB.", 413)

            media_path = f"publicaciones/{uuid.uuid4().hex}_{nombre}"
            almacenamiento = cliente_admin.storage.from_(SUPABASE_STORAGE_BUCKET)
            almacenamiento.upload(
                media_path,
                contenido,
                {"content-type": content_type, "upsert": "false"},
            )
            media_url = almacenamiento.get_public_url(media_path)

        publicacion = {
            "fecha": datetime.now(timezone.utc).isoformat(),
            "titulo": titulo or "Actualización",
            "texto": texto,
            "mediaUrl": media_url,
            "mediaType": media_type,
            "mediaPath": media_path,
            "seccion": seccion,
        }
        creada = cliente_admin.table("publicaciones").insert(publicacion).execute().data
        return jsonify({"success": True, "publicacion": creada[0] if creada else publicacion}), 201
    except Exception as error:
        if media_path:
            try:
                cliente_admin.storage.from_(SUPABASE_STORAGE_BUCKET).remove([media_path])
            except Exception:
                app.logger.exception("No se pudo limpiar un archivo multimedia huérfano")
        app.logger.exception("No se pudo guardar la publicación")
        return respuesta_error(str(error), 500)


@app.route("/api/publicaciones/<publicacion_id>", methods=["DELETE"])
@requiere_admin
def eliminar_publicacion(publicacion_id):
    cliente_admin = supabase_admin
    if cliente_admin is None:
        return respuesta_error(
            "Configura SUPABASE_SERVICE_ROLE_KEY o SUPABASE_KEY con permisos de escritura.",
            503,
        )

    try:
        resultado = (
            cliente_admin.table("publicaciones")
            .delete()
            .eq("id", publicacion_id)
            .execute()
        )
        if not resultado.data:
            return respuesta_error("Publicación no encontrada.", 404)

        media_path = None
        if resultado.data and isinstance(resultado.data[0], dict):
            valor_media_path = resultado.data[0].get("mediaPath")
            if isinstance(valor_media_path, str):
                media_path = valor_media_path
        if media_path:
            cliente_admin.storage.from_(SUPABASE_STORAGE_BUCKET).remove([media_path])
        return jsonify({"success": True})
    except Exception as error:
        app.logger.exception("No se pudo eliminar la publicación")
        return respuesta_error(str(error), 500)