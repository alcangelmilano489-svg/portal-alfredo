import os
import time
from flask import Flask, request, jsonify, send_from_directory, render_template
from werkzeug.utils import secure_filename

base_dir = os.path.abspath(os.path.dirname(__file__))

# Configuramos Flask apuntando explícitamente a carpetas estáticas y de plantillas
app = Flask(__name__, template_folder=base_dir, static_folder=base_dir, static_url_path='')

upload_folder = os.path.join(base_dir, 'uploads')
os.makedirs(upload_folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = upload_folder
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 GB

allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'mkv'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No se encontró el archivo'}), 400
        
        file = request.files['file']
        
        if file and file.filename:
            filename_str = file.filename
            if allowed_file(filename_str):
                safe_name = secure_filename(filename_str)
                filename = f"{int(time.time())}_{safe_name}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                return jsonify({'success': True, 'url': f'/uploads/{filename}'})
        
        return jsonify({'success': False, 'error': 'Archivo no válido o extensión no permitida'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)