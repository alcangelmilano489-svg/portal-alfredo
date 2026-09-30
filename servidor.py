from flask import Flask, jsonify, request

# (Asegúrate de tener inicializado tu app y supabase arriba, por ejemplo:)
# app = Flask(__name__)
# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/api/publicaciones', methods=['GET'])
def obtener_publicaciones():
    try:
        # Consulta a tu tabla en Supabase
        response = supabase.table("publicaciones").select("*").execute()
        return jsonify({"success": True, "publicaciones": response.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})