import hmac
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory
import httpx
from supabase import create_client
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


app = Flask(__name__)

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
if SUPABASE_URL.endswith("/rest/v1"):
    SUPABASE_URL = SUPABASE_URL[:-len("/rest/v1")]
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_WRITE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_READ_KEY = SUPABASE_ANON_KEY
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "media")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

SUPABASE_CONFIG_ERROR = None
supabase = None
supabase_admin = None
if not SUPABASE_URL:
    SUPABASE_CONFIG_ERROR = "Falta configurar SUPABASE_URL en Render."
elif not SUPABASE_READ_KEY:
    SUPABASE_CONFIG_ERROR = "Configura SUPABASE_ANON_KEY para las lecturas."
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_READ_KEY)
        if SUPABASE_WRITE_KEY:
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_WRITE_KEY)
    except Exception:
        app.logger.exception("No se pudo inicializar el cliente Supabase")
        SUPABASE_CONFIG_ERROR = (
            "No se pudo inicializar Supabase; revisa SUPABASE_URL y las claves en Render."
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


def subir_archivo_supabase(bucket, path, nombre, contenido, content_type):
    if not SUPABASE_URL:
        raise RuntimeError("Falta configurar SUPABASE_URL en Render.")
    if not SUPABASE_WRITE_KEY:
        raise RuntimeError("Falta una clave Supabase con permisos de escritura.")

    ruta = "/".join(quote(parte, safe="") for parte in path.split("/"))
    bucket_url = quote(bucket, safe="")
    response = httpx.post(
        f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket_url}/{ruta}",
        headers={
            "apikey": SUPABASE_WRITE_KEY,
            "Authorization": f"Bearer {SUPABASE_WRITE_KEY}",
            "x-upsert": "false",
        },
        files={"file": (nombre, contenido, content_type)},
        timeout=120.0,
    )
    if not response.is_success:
        try:
            detalle = response.json()
        except ValueError:
            detalle = response.text[:1000]
        raise RuntimeError(
            f"Supabase Storage respondió HTTP {response.status_code}: {detalle}"
        )


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
                SUPABASE_CONFIG_ERROR
                or "Configura SUPABASE_SERVICE_ROLE_KEY con rol service_role.",
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
        "realtimeEnabled": bool(SUPABASE_ANON_KEY and SUPABASE_URL),
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
    if supabase is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR or "Supabase no está configurado.", 503
        )

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
            SUPABASE_CONFIG_ERROR
            or "Configura SUPABASE_SERVICE_ROLE_KEY con rol service_role.",
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
            subir_archivo_supabase(
                SUPABASE_STORAGE_BUCKET,
                media_path,
                nombre,
                contenido,
                content_type,
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
            SUPABASE_CONFIG_ERROR
            or "Configura SUPABASE_SERVICE_ROLE_KEY con rol service_role.",
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