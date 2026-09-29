// admin.js
// Sistema de publicación con subida directa de media (video/imagen) al servidor Flask

document.addEventListener("DOMContentLoaded", () => {

    const btnPublicar = document.getElementById("btn-publicar");

    if (btnPublicar) {
        btnPublicar.addEventListener("click", publicarContenido);
    }

});


// ============================================================
// PUBLICAR CONTENIDO
// ============================================================

async function publicarContenido() {

    const inputTitulo = document.getElementById("titulo");
    const inputTexto = document.getElementById("texto");
    const inputArchivo = document.getElementById("archivoVideo");

    const titulo = inputTitulo
        ? inputTitulo.value.trim()
        : "";

    const texto = inputTexto
        ? inputTexto.value.trim()
        : "";


    // --------------------------------------------------------
    // VALIDAR TITULO Y TEXTO
    // --------------------------------------------------------

    if (titulo === "" || texto === "") {

        alert("Por favor completa el título y el contenido.");

        return;
    }


    // --------------------------------------------------------
    // VALIDAR ARCHIVO
    // --------------------------------------------------------

    if (

        !inputArchivo ||
        !inputArchivo.files ||
        inputArchivo.files.length === 0

    ) {

        alert("Por favor selecciona un archivo (video o imagen) de tu galería.");

        return;
    }


    const archivoMedia = inputArchivo.files[0];

    // --------------------------------------------------------
    // MENSAJE DE PROCESAMIENTO
    // --------------------------------------------------------

    const textoOriginalBoton = document.getElementById("btn-publicar")
        ? document.getElementById("btn-publicar").textContent
        : "";

    const btnPublicar = document.getElementById("btn-publicar");

    if (btnPublicar) {

        btnPublicar.disabled = true;

        btnPublicar.textContent = "Subiendo archivo...";
    }


    try {

        // ====================================================
        // CREAR FORMULARIO PARA ENVIAR EL ARCHIVO
        // ====================================================

        const formulario = new FormData();

        formulario.append("archivo", archivoMedia);


        // ====================================================
        // ENVIAR ARCHIVO AL SERVIDOR FLASK
        // ====================================================

        const respuesta = await fetch("/api/subir-video", {

            method: "POST",

            body: formulario

        });


        // ====================================================
        // COMPROBAR RESPUESTA DEL SERVIDOR
        // ====================================================

        if (!respuesta.ok) {

            throw new Error(
                "El servidor no pudo recibir el archivo."
            );
        }


        const resultado = await respuesta.json();


        if (!resultado.ok) {

            throw new Error(
                resultado.mensaje ||
                "No se pudo subir el archivo."
            );
        }


        // ====================================================
        // URL DEL ARCHIVO GUARDADO
        // ====================================================

        const urlMedia = resultado.url;

        // Detectar tipo desde la extensión de la URL devuelta por el servidor
        const extension = urlMedia.split('.').pop().toLowerCase();
        const videoExts = ['mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv', 'flv', 'wmv'];
        const mediaType = videoExts.includes(extension) ? "video" : "image";


        // ====================================================
        // OBTENER PUBLICACIONES EXISTENTES
        // ====================================================

        let publicaciones = [];

        try {

            publicaciones =
                JSON.parse(
                    localStorage.getItem("portal_noticias")
                ) || [];

        } catch (error) {

            publicaciones = [];
        }


        // ====================================================
        // CREAR NUEVA PUBLICACIÓN
        // ====================================================

        const nuevaPublicacion = {

            titulo: titulo,

            categoria: mediaType === "video" ? "Video" : "Imagen",

            texto: texto,

            // Guardamos solamente su dirección
            mediaUrl: urlMedia,

            mediaType: mediaType,

            fecha: new Date().toLocaleDateString()

        };


        // ====================================================
        // AGREGAR PUBLICACIÓN
        // ====================================================

        publicaciones.unshift(nuevaPublicacion);


        // ====================================================
        // GUARDAR SOLO LOS DATOS DE LA PUBLICACIÓN
        // ====================================================

        localStorage.setItem(
            "portal_noticias",
            JSON.stringify(publicaciones)
        );


        // ====================================================
        // RESTAURAR BOTÓN
        // ====================================================

        if (btnPublicar) {

            btnPublicar.disabled = false;

            btnPublicar.textContent =
                textoOriginalBoton || "Guardar y Publicar";
        }


        // ====================================================
        // MENSAJE DE ÉXITO
        // ====================================================

        alert("¡Archivo subido y publicado exitosamente!");


        // ====================================================
        // IR A LA PÁGINA PRINCIPAL
        // ====================================================

        window.location.href = "index.html";


    } catch (error) {

        console.error(
            "Error al publicar el archivo:",
            error
        );


        // Restaurar botón

        if (btnPublicar) {

            btnPublicar.disabled = false;

            btnPublicar.textContent =
                textoOriginalBoton || "Guardar y Publicar";
        }


        // Mostrar error

        alert(
            "No se pudo subir el archivo.\n\n" +
            "Detalle: " +
            error.message
        );
    }

}
