document.addEventListener('DOMContentLoaded', function() {
    // Ajusta el selector según el ID de tu formulario de subida o botón
    const uploadForm = document.getElementById('uploadForm') || document.getElementById('form-admin-noticia');
    const fileInput = document.getElementById('fileInput') || document.getElementById('admin-media');

    if (uploadForm && fileInput) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            if (!fileInput.files || fileInput.files.length === 0) {
                alert("Por favor selecciona un archivo multimedia primero.");
                return;
            }

            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('file', file);

            try {
                console.log("Subiendo archivo pesado al servidor...");
                
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                // NUEVA MEJORA: Validamos si la respuesta HTTP fue exitosa
                if (!response.ok) {
                    throw new Error(`Error en el servidor (Código ${response.status}): El archivo puede ser demasiado pesado o la conexión se interrumpió.`);
                }

                // Obtenemos el texto plano primero para evitar fallos si el servidor responde en blanco
                const responseText = await response.text();
                if (!responseText) {
                    throw new Error("El servidor respondió con un contenido vacío (posible límite superado o error interno).");
                }

                const result = JSON.parse(responseText);

                if (result.success) {
                    console.log("¡Archivo subido con éxito!", result.url);
                    alert("¡Archivo subido correctamente!");
                    
                    // Opcional: guardar la referencia en localStorage si estás manejando publicaciones locales
                    var mediaType = file.type.startsWith('video') ? 'video' : 'image';
                    var nuevaPublicacion = {
                        id: 'post_' + Date.now(),
                        mediaUrl: result.url,
                        mediaType: mediaType,
                        fecha: new Date().toLocaleDateString()
                    };

                    var publicaciones = JSON.parse(localStorage.getItem('portal_noticias')) || [];
                    publicaciones.unshift(nuevaPublicacion);
                    localStorage.setItem('portal_noticias', JSON.stringify(publicaciones));

                    uploadForm.reset();
                } else {
                    console.error("Error del servidor:", result.error);
                    alert("Error al subir: " + result.error);
                }

            } catch (error) {
                console.error("Error de conexión:", error);
                alert("Error: " + error.message);
            }
        });
    }
});