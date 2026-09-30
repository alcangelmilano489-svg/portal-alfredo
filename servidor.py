import os
import uuid
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client

# ============================================================
# CONFIGURACIÓN DE SUPABASE
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ggeevxhnhsfvtwjdmssz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# CONFIGURACIÓN DE CLOUDINARY
# ============================================================

cloudinary.config(
    cloud_name="cj5tfi7j",
    api_key="611496724184694",
    api_secret="mJoTfVqesdDJt5vAIPl720yDvZ8",
)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

# Configuración opcional para permitir archivos grandes sin restricciones (ej: 500MB)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024


# ============================================================
# TIPOS PERMITIDOS
# ============================================================

EXTENSIONES_IMAGEN = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "bmp",
    "svg"
}


EXTENSIONES_VIDEO = {
    "mp4",
    "webm",
    "mov",
    "avi",
    "mkv",
    "m4v",
    "3gp",
    "mpeg",
    "mpg"
}


EXTENSIONES_PERMITIDAS = (
    EXTENSIONES_IMAGEN |
    EXTENSIONES_VIDEO
)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def obtener_extension(nombre):

    if not nombre:
        return ""

    if "." not in nombre:
        return ""

    return nombre.rsplit(".", 1)[1].lower()


def tipo_archivo(nombre):

    extension = obtener_extension(nombre)

    if extension in EXTENSIONES_VIDEO:
        return "video"

    if extension in EXTENSIONES_IMAGEN:
        return "imagen"

    return "desconocido"


def archivo_permitido(nombre):

    extension = obtener_extension(nombre)

    return extension in EXTENSIONES_PERMITIDAS


def cargar_publicaciones():
    """Obtiene todas las publicaciones desde la base de datos de Supabase."""
    try:
        response = supabase.table("publicaciones").select("*").order("fecha", desc=True).execute()
        return response.data if response.data else []
    except Exception as error:
        print("ERROR LEYENDO PUBLICACIONES DE SUPABASE:", error)
        return []


def guardar_publicacion_supabase(publicacion):
    """Inserta una nueva publicación en la tabla de Supabase."""
    try:
        response = supabase.table("publicaciones").insert(publicacion).execute()
        return response.data
    except Exception as error:
        print("ERROR GUARDANDO EN SUPABASE:", error)
        raise error


# ============================================================
# CORS
# ============================================================

@app.after_request
def agregar_cors(respuesta):

    respuesta.headers["Access-Control-Allow-Origin"] = "*"

    respuesta.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, DELETE, OPTIONS"
    )

    respuesta.headers["Access-Control-Allow-Headers"] = (
        "Content-Type"
    )

    return respuesta


# ============================================================
# INICIO Y PANEL DE ADMINISTRACIÓN
# ============================================================

@app.route("/")
def inicio():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/index.html")
def pagina_principal():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/admin")
def panel_admin():
    try:
        ruta_archivo = os.path.join(BASE_DIR, "admin.html")
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"No se pudo cargar el panel admin. Error: {str(e)}", 404


# ============================================================
# ESTADO DEL SERVIDOR
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "success": True,
        "status": "online"
    })


# ============================================================
# SUBIR IMAGEN O VIDEO A CLOUDINARY Y SUPABASE
# ============================================================

@app.route("/upload", methods=["POST", "OPTIONS"])
def upload():

    if request.method == "OPTIONS":

        return "", 204

    try:

        if "file" not in request.files:

            return jsonify({
                "success": False,
                "error": "No se recibió ningún archivo."
            }), 400

        archivo = request.files["file"]

        nombre_original = archivo.filename or ""

        if not nombre_original:

            return jsonify({
                "success": False,
                "error": "No se seleccionó ningún archivo."
            }), 400

        if not archivo_permitido(nombre_original):

            return jsonify({
                "success": False,
                "error": "Tipo de archivo no permitido."
            }), 400

        tipo = tipo_archivo(nombre_original)
        extension = obtener_extension(nombre_original)
        identificador = uuid.uuid4().hex

        print("")
        print("======================================")
        print("SUBIENDO A CLOUDINARY")
        print("Archivo:", nombre_original)
        print("Tipo:", tipo)
        print("======================================")
        print("")

        resultado_cloudinary = cloudinary.uploader.upload(
            archivo,
            resource_type="auto",
            folder="portal_alfredo"
        )

        url_nube = resultado_cloudinary.get("secure_url")
        public_id = resultado_cloudinary.get("public_id")
        tamaño = resultado_cloudinary.get("bytes", 0)

        if not url_nube:

            return jsonify({
                "success": False,
                "error": "No se pudo subir el archivo a Cloudinary."
            }), 500

        publicacion = {
            "id": identificador,
            "nombre": nombre_original,
            "archivo": public_id,
            "tipo": tipo,
            "extension": extension,
            "tamaño": tamaño,
            "url": url_nube,
            "fecha": __import__("datetime").datetime.now().isoformat()
        }

        # Guardar directamente en la base de datos de Supabase
        guardar_publicacion_supabase(publicacion)

        return jsonify({
            "success": True,
            "mensaje": "Archivo publicado correctamente en Supabase y Cloudinary.",
            "id": identificador,
            "url": url_nube,
            "filename": public_id,
            "tipo": tipo,
            "publicacion": publicacion
        })

    except Exception as error:

        print("")
        print("ERROR EN /upload:")
        print(error)
        print("")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ============================================================
# OBTENER TODAS LAS PUBLICACIONES
# ============================================================

@app.route("/api/publicaciones", methods=["GET"])
def publicaciones():

    try:

        datos = cargar_publicaciones()

        return jsonify({
            "success": True,
            "publicaciones": datos
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error),
            "publicaciones": []
        }), 500


# ============================================================
# SERVIR ARCHIVOS ESTÁTICOS / CSS / JS / IMÁGENES LOCALES
# ============================================================

@app.route("/<path:nombre>")
def servir_archivo(nombre):
    return send_from_directory(BASE_DIR, nombre, conditional=True)


# ============================================================
# ELIMINAR PUBLICACIÓN
# ============================================================

@app.route("/api/publicaciones/<id_publicacion>", methods=["DELETE", "OPTIONS"])
def eliminar_publicacion(id_publicacion):

    if request.method == "OPTIONS":

        return "", 204

    try:
        # Eliminar el registro directamente de la tabla en Supabase
        response = supabase.table("publicaciones").delete().eq("id", str(id_publicacion)).execute()

        return jsonify({
            "success": True,
            "mensaje": "Publicación eliminada de Supabase."
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ============================================================
# EJECUTAR SERVIDOR
# ============================================================

if __name__ == "__main__":

    puerto = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    print("")
    print("======================================")
    print("SERVIDOR ALFREDO MANEIRO (SUPABASE)")
    print("======================================")
    print("Puerto:", puerto)
    print("Servidor iniciado.")
    print("======================================")
    print("")

    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=False,
        threaded=True
    )