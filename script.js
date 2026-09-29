document.addEventListener("DOMContentLoaded", function () {

    const uploadForm = document.getElementById("uploadForm") ||
                       document.getElementById("form-admin-noticia");

    const fileInput = document.getElementById("fileInput") ||
                      document.getElementById("admin-media");

    if (!uploadForm || !fileInput) {
        console.log("No se encontro el formulario de subida.");
        return;
    }

    uploadForm.addEventListener("submit", function (event) {

        event.preventDefault();

        if (!fileInput.files || fileInput.files.length === 0) {
            alert("Selecciona una imagen o un video.");
            return;
        }

        const file = fileInput.files[0];

        const formData = new FormData();
        formData.append("file", file);

        const xhr = new XMLHttpRequest();

        xhr.open("POST", "/upload", true);

        xhr.upload.addEventListener("progress", function (event) {

            if (event.lengthComputable) {

                const porcentaje =
                    Math.round((event.loaded / event.total) * 100);

                console.log("Subiendo: " + porcentaje + "%");

            } else {

                console.log("Subiendo archivo...");

            }

        });

        xhr.onload = function () {

            if (xhr.status >= 200 && xhr.status < 300) {

                let resultado;

                try {

                    resultado = JSON.parse(xhr.responseText);

                } catch (error) {

                    console.error("Respuesta del servidor:", xhr.responseText);

                    alert("El servidor envio una respuesta incorrecta.");
                    return;
                }

                if (resultado.success) {

                    alert("Archivo subido correctamente.");

                    console.log("Archivo:", resultado.url);

                    const tipo = file.type.startsWith("video/")
                        ? "video"
                        : "image";

                    const publicacion = {
                        id: "post_" + Date.now(),
                        mediaUrl: resultado.url,
                        mediaType: tipo,
                        nombre: file.name,
                        fecha: new Date().toISOString()
                    };

                    let publicaciones = [];

                    try {

                        publicaciones =
                            JSON.parse(
                                localStorage.getItem("portal_noticias")
                            ) || [];

                    } catch (error) {

                        publicaciones = [];

                    }

                    publicaciones.unshift(publicacion);

                    localStorage.setItem(
                        "portal_noticias",
                        JSON.stringify(publicaciones)
                    );

                    uploadForm.reset();

                } else {

                    alert(
                        "Error al subir el archivo: " +
                        (resultado.error || "Error desconocido")
                    );
                }

            } else {

                alert(
                    "El servidor rechazo el archivo. Codigo: " +
                    xhr.status
                );

                console.error(
                    "Error HTTP:",
                    xhr.status,
                    xhr.responseText
                );
            }
        };

        xhr.onerror = function () {

            alert(
                "No se pudo conectar con el servidor."
            );

            console.error(
                "Error de conexion durante la subida."
            );
        };

        xhr.onabort = function () {

            alert(
                "La subida fue cancelada."
            );

        };

        xhr.send(formData);

    });

});