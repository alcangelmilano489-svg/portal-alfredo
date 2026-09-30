from flask import Flask, jsonify, request
import os
from supabase import create_client, Client

# 1. Aquí es donde se inicializa 'app' (asegúrate de que esto esté arriba)
app = Flask(__name__)

# 2. Aquí es donde se inicializa 'supabase' con tus variables de entorno (más arriba en tu archivo)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if SUPABASE_URL is None or SUPABASE_KEY is None:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ... (todo el código intermedio que ya tengas en tu servidor.py) ...

# 3. Y esta es la ruta nueva, colócala AL FINAL del archivo para que 'app' y 'supabase' ya existan:
@app.route('/api/publicaciones', methods=['GET'])
def obtener_publicaciones():
    try:
        response = supabase.table("publicaciones").select("*").execute()
        return jsonify({"success": True, "publicaciones": response.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})