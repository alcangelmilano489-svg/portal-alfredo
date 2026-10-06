import hmac
import os
import uuid
import re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from collections.abc import Sequence
from typing import Any
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
SECCIONES_EDITORIALES = {"vida", "obra"}
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


def encabezados_supabase_admin():
    if not SUPABASE_WRITE_KEY:
        raise RuntimeError("Falta una clave Supabase con permisos de escritura.")
    headers = {"apikey": SUPABASE_WRITE_KEY}
    if not SUPABASE_WRITE_KEY.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {SUPABASE_WRITE_KEY}"
    return headers


def solicitar_supabase_admin(
    metodo, recurso, prefer="return=representation", **kwargs
) -> list[dict[str, Any]]:
    headers = encabezados_supabase_admin()
    headers.update({"Content-Type": "application/json", "Prefer": prefer})
    response = httpx.request(
        metodo,
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/{recurso}",
        headers=headers,
        timeout=30.0,
        **kwargs,
    )
    if not response.is_success:
        try:
            detalle = response.json()
        except ValueError:
            detalle = response.text[:1000]
        raise RuntimeError(f"Supabase respondió HTTP {response.status_code}: {detalle}")
    return response.json()


def contar_suscriptores():
    headers = encabezados_supabase_admin()
    headers["Prefer"] = "count=exact"
    response = httpx.get(
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/suscriptores",
        params={"select": "id"},
        headers={**headers, "Range": "0-0"},
        timeout=15.0,
    )
    if not response.is_success:
        raise RuntimeError("No se pudo consultar el total de suscriptores.")

    coincidencia = re.search(r"/(\d+)$", response.headers.get("content-range", ""))
    if not coincidencia:
        raise RuntimeError("Supabase no devolvió el total de suscriptores.")
    return int(coincidencia.group(1))


def subir_archivo_supabase(bucket, path, nombre, contenido, content_type):
    if not SUPABASE_URL:
        raise RuntimeError("Falta configurar SUPABASE_URL en Render.")
    if not SUPABASE_WRITE_KEY:
        raise RuntimeError("Falta una clave Supabase con permisos de escritura.")

    ruta = "/".join(quote(parte, safe="") for parte in path.split("/"))
    bucket_url = quote(bucket, safe="")
    headers = encabezados_supabase_admin()
    headers["x-upsert"] = "false"

    response = httpx.post(
        f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket_url}/{ruta}",
        headers=headers,
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


@app.route("/robots.txt")
def robots_txt():
    contenido = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Sitemap: https://alfredomaneiro.org.ve/sitemap.xml\n"
    )
    return contenido, 200, {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=0, must-revalidate",
    }


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


@app.route("/api/secciones", methods=["GET"])
def obtener_contenido_secciones():
    if supabase is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR or "Supabase no está configurado.", 503
        )

    try:
        filas = (
            supabase.table("contenido_secciones")
            .select("seccion,contenido,updated_at")
            .in_("seccion", sorted(SECCIONES_EDITORIALES))
            .execute()
            .data
        )
        contenido = {seccion: None for seccion in SECCIONES_EDITORIALES}
        for fila in filas:
            seccion = fila.get("seccion")
            if seccion in SECCIONES_EDITORIALES:
                contenido[seccion] = fila.get("contenido") or ""
        return jsonify({"success": True, "secciones": contenido})
    except Exception:
        app.logger.exception("No se pudo cargar el contenido editorial")
        return respuesta_error("No se pudo cargar el contenido de las secciones.", 500)


@app.route("/api/secciones/<seccion>", methods=["PUT"])
@requiere_admin
def actualizar_contenido_seccion(seccion):
    if seccion not in SECCIONES_EDITORIALES:
        return respuesta_error("Sección editorial no válida.", 404)

    datos = request.get_json(silent=True) or {}
    contenido = datos.get("contenido")
    if not isinstance(contenido, str):
        return respuesta_error("El contenido debe ser texto.", 400)
    if len(contenido) > 100000:
        return respuesta_error("El texto supera el límite de 100 000 caracteres.", 413)

    actualizado = datetime.now(timezone.utc).isoformat()
    fila = {"seccion": seccion, "contenido": contenido, "updated_at": actualizado}
    try:
        if SUPABASE_WRITE_KEY and SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            filas = solicitar_supabase_admin(
                "POST",
                "contenido_secciones",
                params={"on_conflict": "seccion"},
                json=fila,
                prefer="resolution=merge-duplicates,return=representation",
            )
        else:
            filas = (
                supabase_admin.table("contenido_secciones")
                .upsert(fila, on_conflict="seccion")
                .execute()
                .data
            )
        guardada = filas[0] if filas else fila
        return jsonify({
            "success": True,
            "seccion": seccion,
            "contenido": guardada.get("contenido", contenido),
            "updated_at": guardada.get("updated_at", actualizado),
        })
    except Exception:
        app.logger.exception("No se pudo guardar el contenido editorial")
        return respuesta_error("No se pudo guardar el contenido de la sección.", 500)


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


def uuid_publicacion_valido(publicacion_id):
    try:
        return str(uuid.UUID(publicacion_id))
    except (AttributeError, TypeError, ValueError):
        return None


@app.route("/api/publicaciones/<publicacion_id>/comentarios", methods=["GET"])
def obtener_comentarios(publicacion_id):
    if supabase is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR or "Supabase no está configurado.", 503
        )

    publicacion_uuid = uuid_publicacion_valido(publicacion_id)
    if publicacion_uuid is None:
        return respuesta_error("Publicación no válida.", 400)

    try:
        comentarios = (
            supabase.table("comentarios")
            .select("id,nombre,texto,created_at")
            .eq("publicacion_id", publicacion_uuid)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        return jsonify({"success": True, "comentarios": comentarios})
    except Exception:
        app.logger.exception("No se pudieron consultar los comentarios")
        return respuesta_error("No se pudieron cargar los comentarios.", 500)


@app.route("/api/publicaciones/<publicacion_id>/comentarios", methods=["POST"])
def crear_comentario(publicacion_id):
    if supabase_admin is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Configura SUPABASE_SERVICE_ROLE_KEY para guardar comentarios.",
            503,
        )

    publicacion_uuid = uuid_publicacion_valido(publicacion_id)
    if publicacion_uuid is None:
        return respuesta_error("Publicación no válida.", 400)

    datos = request.get_json(silent=True) or {}
    texto = datos.get("texto", "")
    nombre = datos.get("nombre", "Visitante")
    if not isinstance(texto, str) or not texto.strip() or len(texto.strip()) > 1000:
        return respuesta_error("El comentario debe tener entre 1 y 1000 caracteres.", 400)
    if not isinstance(nombre, str) or len(nombre.strip()) > 80:
        return respuesta_error("El nombre no puede superar 80 caracteres.", 400)

    comentario = {
        "publicacion_id": publicacion_uuid,
        "nombre": nombre.strip() or "Visitante",
        "texto": texto.strip(),
    }
    try:
        if SUPABASE_WRITE_KEY and SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            guardados = solicitar_supabase_admin(
                "POST", "comentarios", json=comentario
            )
        else:
            guardados = (
                supabase_admin.table("comentarios")
                .insert(comentario)
                .execute()
                .data
            )
        return jsonify({"success": True, "comentario": guardados[0] if guardados else comentario}), 201
    except Exception:
        app.logger.exception("No se pudo guardar el comentario")
        return respuesta_error("No se pudo guardar el comentario.", 500)


@app.route("/api/suscripciones/count", methods=["GET"])
def obtener_total_suscriptores():
    if supabase_admin is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Configura SUPABASE_SERVICE_ROLE_KEY para consultar suscripciones.",
            503,
        )
    try:
        return jsonify({"success": True, "count": contar_suscriptores()})
    except Exception:
        app.logger.exception("No se pudo consultar el total de suscriptores")
        return respuesta_error("No se pudo consultar el total de suscriptores.", 500)


@app.route("/api/suscripciones", methods=["POST"])
def crear_suscripcion():
    if supabase_admin is None:
        return respuesta_error(
            SUPABASE_CONFIG_ERROR
            or "Configura SUPABASE_SERVICE_ROLE_KEY para guardar suscripciones.",
            503,
        )

    datos = request.get_json(silent=True) or {}
    correo = datos.get("email", "")
    if not isinstance(correo, str):
        return respuesta_error("Escribe un correo electrónico válido.", 400)
    correo = correo.strip().lower()
    if len(correo) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        return respuesta_error("Escribe un correo electrónico válido.", 400)

    try:
        creada = solicitar_supabase_admin(
            "POST",
            "suscriptores",
            params={"on_conflict": "email"},
            json={"email": correo},
            prefer="resolution=ignore-duplicates,return=representation",
        )
        return jsonify({"success": True, "alreadySubscribed": not bool(creada)}), 200
    except Exception:
        app.logger.exception("No se pudo guardar la suscripción")
        return respuesta_error("No se pudo completar la suscripción.", 500)


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
            "id": str(uuid.uuid4()),
            "fecha": datetime.now(timezone.utc).isoformat(),
            "titulo": titulo or "Actualización",
            "texto": texto,
            "mediaUrl": media_url,
            "mediaType": media_type,
            "mediaPath": media_path,
            "seccion": seccion,
        }
        if SUPABASE_WRITE_KEY and SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            creada = solicitar_supabase_admin(
                "POST", "publicaciones", json=publicacion
            )
        else:
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
        publicaciones: Sequence[Any]
        if SUPABASE_WRITE_KEY and SUPABASE_WRITE_KEY.startswith("sb_secret_"):
            publicaciones = solicitar_supabase_admin(
                "DELETE",
                "publicaciones",
                params={"id": f"eq.{publicacion_id}"},
            )
        else:
            publicaciones = (
                cliente_admin.table("publicaciones")
                .delete()
                .eq("id", publicacion_id)
                .execute()
                .data
            )
        if not publicaciones:
            return respuesta_error("Publicación no encontrada.", 404)

        media_path = None
        if isinstance(publicaciones[0], dict):
            valor_media_path = publicaciones[0].get("mediaPath")
            if isinstance(valor_media_path, str):
                media_path = valor_media_path
        if media_path:
            cliente_admin.storage.from_(SUPABASE_STORAGE_BUCKET).remove([media_path])
        return jsonify({"success": True})
    except Exception as error:
        app.logger.exception("No se pudo eliminar la publicación")
        return respuesta_error(str(error), 500)
