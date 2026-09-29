import os
import json
import uuid

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

DATA_FOLDER = os.path.join(BASE_DIR, "data")

POSTS_FILE = os.path.join(DATA_FOLDER, "publicaciones.json")


os.makedirs(UPLOAD_FOLDER, exist_ok=True)

os.makedirs(DATA_FOLDER, exist_ok=True)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# IMPORTANTE:
# No colocamos MAX_CONTENT_LENGTH.
# Flask no impondrá un límite de tamaño propio.
#
# El límite real dependerá del servidor/hosting que utilices.


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
# FUNCIONES
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

    if not os.path.exists(POSTS_FILE):
        return []

    try:

        with open(
            POSTS_FILE,
            "r",
            encoding="utf-8"
        ) as archivo:

            contenido = archivo.read().strip()

            if not contenido:
                return []

            datos = json.loads(contenido)

            if isinstance(datos, list):
                return datos

            return []

    except Exception as error:

        print("ERROR LEYENDO PUBLICACIONES:", error)

        return []


def guardar_publicaciones(publicaciones):

    archivo_temporal = POSTS_FILE + ".tmp"

    with open(
        archivo_temporal,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            publicaciones,
            archivo,
            ensure_ascii=False,
            indent=2
        )


    os.replace(
        archivo_temporal,
        POSTS_FILE
    )


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
# INICIO
# ============================================================

@app.route("/")
def inicio():

    return jsonify({
        "success": True,
        "mensaje": "Servidor funcionando correctamente"
    })


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
# SUBIR IMAGEN O VIDEO
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


        # Evita el problema str | None de VS Code
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


        nombre_seguro = secure_filename(
            nombre_original
        )


        if not nombre_seguro:

            return jsonify({
                "success": False,
                "error": "El nombre del archivo no es válido."
            }), 400


        extension = obtener_extension(
            nombre_seguro
        )


        tipo = tipo_archivo(
            nombre_seguro
        )


        # Nombre único para evitar reemplazar archivos
        identificador = uuid.uuid4().hex


        nombre_final = (
            identificador
            + "_"
            + nombre_seguro
        )


        ruta_archivo = os.path.join(
            UPLOAD_FOLDER,
            nombre_final
        )


        print("")
        print("======================================")
        print("NUEVA SUBIDA")
        print("Archivo:", nombre_original)
        print("Tipo:", tipo)
        print("Destino:", ruta_archivo)
        print("======================================")
        print("")


        # Guarda directamente en disco
        archivo.save(ruta_archivo)


        if not os.path.exists(ruta_archivo):

            return jsonify({
                "success": False,
                "error": "No se pudo guardar el archivo."
            }), 500


        tamaño = os.path.getsize(
            ruta_archivo
        )


        # ====================================================
        # CREAR PUBLICACIÓN
        # ====================================================

        publicacion = {

            "id": identificador,

            "nombre": nombre_original,

            "archivo": nombre_final,

            "tipo": tipo,

            "extension": extension,

            "tamaño": tamaño,

            "url": "/uploads/" + nombre_final,

            "fecha": __import__("datetime")
                .datetime.now()
                .isoformat()

        }


        publicaciones = cargar_publicaciones()


        publicaciones.insert(
            0,
            publicacion
        )


        guardar_publicaciones(
            publicaciones
        )


        return jsonify({

            "success": True,

            "mensaje": "Archivo publicado correctamente.",

            "id": identificador,

            "url": "/uploads/" + nombre_final,

            "filename": nombre_final,

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
# SERVIR IMÁGENES Y VIDEOS
# ============================================================

@app.route("/uploads/<path:nombre>")
def servir_archivo(nombre):

    return send_from_directory(

        UPLOAD_FOLDER,

        nombre,

        conditional=True

    )


# ============================================================
# ELIMINAR PUBLICACIÓN
# ============================================================

@app.route(
    "/api/publicaciones/<id_publicacion>",
    methods=["DELETE", "OPTIONS"]
)
def eliminar_publicacion(id_publicacion):

    if request.method == "OPTIONS":

        return "", 204


    try:

        publicaciones = cargar_publicaciones()


        encontrada = None

        restantes = []


        for publicacion in publicaciones:

            if str(publicacion.get("id")) == str(
                id_publicacion
            ):

                encontrada = publicacion

            else:

                restantes.append(publicacion)


        if encontrada is None:

            return jsonify({

                "success": False,

                "error": "Publicación no encontrada."

            }), 404


        nombre_archivo = encontrada.get(
            "archivo"
        )


        if nombre_archivo:

            ruta = os.path.join(
                UPLOAD_FOLDER,
                nombre_archivo
            )


            if os.path.exists(ruta):

                os.remove(ruta)


        guardar_publicaciones(
            restantes
        )


        return jsonify({

            "success": True,

            "mensaje": "Publicación eliminada."

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
    print("SERVIDOR ALFREDO MANEIRO")
    print("======================================")
    print("Puerto:", puerto)
    print("Carpeta de archivos:", UPLOAD_FOLDER)
    print("Servidor iniciado.")
    print("======================================")
    print("")


    app.run(

        host="0.0.0.0",

        port=puerto,

        debug=False,

        threaded=True

    )