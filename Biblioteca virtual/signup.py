import os
import uuid

from datetime import date
from flask import abort, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image

from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import bcrypt

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

UPLOAD_ROOT = os.path.join(app.root_path, "uploads")
PORTADAS_FOLDER = os.path.join(
    app.static_folder, "uploads", "portadas"
)
LIBROS_FOLDER = os.path.join(UPLOAD_ROOT, "libros")

os.makedirs(PORTADAS_FOLDER, exist_ok=True)
os.makedirs(LIBROS_FOLDER, exist_ok=True)

app.secret_key = "bb04cbed8229b36cde411d7129bd0c005d7944305bf7b1b3c0f3bc27f797d5e6"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "JdHaCaRu74916",
    "database": "biblioteca",
}

def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if "id_usuario" not in session:
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return envoltura


@app.route("/")
def inicio():
    return render_template("biblioteca_virtual.html")


@app.route("/biblioteca")
def biblioteca():
    return redirect(url_for("inicio"))



@app.route("/registro", methods=["GET", "POST"])
def registro():
    mensaje, ok = None, False

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("clave", "")
        confirmar = request.form.get("clave2", "")

        if not correo or not contrasena or not confirmar:
            mensaje = "Completa todos los campos."

        elif contrasena != confirmar:
            mensaje = "Las contraseñas no coinciden."

        elif len(contrasena) < 8:
            mensaje = "La contraseña debe tener al menos 8 caracteres."

        elif len(contrasena.encode("utf-8")) > 72:
            mensaje = "La contraseña es demasiado larga."

        else:
            hash_pw = bcrypt.hashpw(
                contrasena.encode("utf-8"),
                bcrypt.gensalt()
            ).decode("utf-8")

            conexion = None

            try:
                conexion = mysql.connector.connect(**DB_CONFIG)
                cursor = conexion.cursor()

                cursor.execute(
                    """
                    INSERT INTO usuarios (correo, contraseña)
                    VALUES (%s, %s)
                    """,
                    (correo, hash_pw)
                )

                conexion.commit()
                mensaje = "Cuenta creada. Ya puedes iniciar sesión."
                ok = True

            except mysql.connector.IntegrityError:
                mensaje = "Ese correo ya está registrado."

            except mysql.connector.Error:
                app.logger.exception("Error al registrar usuario")
                mensaje = "No se pudo completar el registro."

            finally:
                if conexion is not None and conexion.is_connected():
                    conexion.close()

    return render_template(
        "sign up.html",
        mensaje=mensaje,
        ok=ok
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    mensaje = None

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("clave", "")

        conexion = None
        fila = None

        try:
            conexion = mysql.connector.connect(**DB_CONFIG)
            cursor = conexion.cursor()

            cursor.execute(
                """
                SELECT id_usuario, contraseña
                FROM usuarios
                WHERE correo = %s
                """,
                (correo,)
            )

            fila = cursor.fetchone()

        except mysql.connector.Error:
            app.logger.exception("Error al iniciar sesión")
            mensaje = "No se pudo conectar con el sistema."

        finally:
            if conexion is not None and conexion.is_connected():
                conexion.close()

        if mensaje is None:
            if (
                fila
                and len(contrasena.encode("utf-8")) <= 72
                and bcrypt.checkpw(
                    contrasena.encode("utf-8"),
                    fila[1].encode("utf-8")
                )
            ):
                session.clear()
                session["id_usuario"] = fila[0]

                return redirect(url_for("biblioteca_usuario"))

            mensaje = "Correo o contraseña incorrectos."

    return render_template("login.html", mensaje=mensaje)


@app.route("/panel")
@login_requerido
def panel():
    return render_template(
        "panel.html",
        nombres=session.get("nombres", "")
    )


# Cerrar sesión
@app.route("/logout", methods=["POST"])
@login_requerido
def logout():
    session.clear()
    return redirect(url_for("inicio"))

@app.route("/mainpage")
@login_requerido
def biblioteca_usuario():
    conexion = None

    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)

        busqueda = request.args.get("q", "").strip()

        if busqueda:
            termino = f"%{busqueda}%"

            cursor.execute(
                """
                SELECT id_libro, titulo, autor, categoria,
                       editorial, ano_publicacion, cantidad,
                       imagen_portada
                FROM libros
                WHERE titulo LIKE %s
                   OR autor LIKE %s
                   OR categoria LIKE %s
                ORDER BY id_libro DESC
                """,
                (termino, termino, termino)
            )
        else:
            cursor.execute(
                """
                SELECT id_libro, titulo, autor, categoria,
                       editorial, ano_publicacion, cantidad,
                       imagen_portada
                FROM libros
                ORDER BY id_libro DESC
                """
            )

        libros = cursor.fetchall()

    except mysql.connector.Error:
        app.logger.exception("Error al consultar los libros")
        libros = []

    finally:
        if conexion is not None and conexion.is_connected():
            conexion.close()

    return render_template("mainpage.html", libros=libros)


@app.route("/publicar", methods=["GET", "POST"])
@login_requerido
def publicar_libro():
    mensaje = None

    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        categoria = request.form.get("categoria", "").strip()
        editorial = request.form.get("editorial", "").strip()
        ano_texto = request.form.get("ano_publicacion", "").strip()
        cantidad_texto = request.form.get("cantidad", "").strip()

        portada = request.files.get("imagen_portada")
        archivo_pdf = request.files.get("libro")

        # Validar los campos obligatorios.
        if not all([titulo, autor, categoria, editorial]):
            mensaje = "Completa todos los campos obligatorios."

        elif not portada or not portada.filename:
            mensaje = "Selecciona una imagen de portada."

        elif not archivo_pdf or not archivo_pdf.filename:
            mensaje = "Selecciona el archivo PDF del libro."

        else:
            try:
                ano = int(ano_texto) if ano_texto else None
                cantidad = int(cantidad_texto)

                if ano is not None and not (
                    1901 <= ano <= date.today().year
                ):
                    raise ValueError

                if cantidad < 1:
                    raise ValueError

            except ValueError:
                mensaje = "Revisa el año y la cantidad de ejemplares."

            if mensaje is None:
                nombre_portada = secure_filename(portada.filename)
                nombre_pdf = secure_filename(archivo_pdf.filename)

                extension_imagen = os.path.splitext(
                    nombre_portada
                )[1].lower()

                extension_pdf = os.path.splitext(
                    nombre_pdf
                )[1].lower()

                if extension_imagen not in {
                    ".jpg", ".jpeg", ".png", ".webp"
                }:
                    mensaje = (
                        "La portada debe ser JPG, PNG o WEBP."
                    )

                elif extension_pdf != ".pdf":
                    mensaje = "El libro debe estar en formato PDF."

                else:
                    # Comprobar que el archivo realmente sea una imagen.
                    try:
                        portada.stream.seek(0)

                        with Image.open(portada.stream) as imagen:
                            if imagen.format not in {
                                "JPEG", "PNG", "WEBP"
                            }:
                                raise ValueError

                            imagen.verify()

                        portada.stream.seek(0)

                    except Exception:
                        mensaje = "La imagen de portada no es válida."

                    # Comprobar la firma del archivo PDF.
                    if mensaje is None:
                        archivo_pdf.stream.seek(0)
                        firma = archivo_pdf.stream.read(5)
                        archivo_pdf.stream.seek(0)

                        if firma != b"%PDF-":
                            mensaje = "El archivo seleccionado no es un PDF válido."

                if mensaje is None:
                    # Generar nombres únicos para evitar sobrescrituras.
                    nombre_unico_portada = (
                        f"{uuid.uuid4().hex}{extension_imagen}"
                    )
                    nombre_unico_pdf = (
                        f"{uuid.uuid4().hex}.pdf"
                    )

                    ruta_portada = os.path.join(
                        PORTADAS_FOLDER, nombre_unico_portada
                    )
                    ruta_pdf = os.path.join(
                        LIBROS_FOLDER, nombre_unico_pdf
                    )

                    conexion = None
                    portada_guardada = False
                    pdf_guardado = False

                    try:
                        portada.save(ruta_portada)
                        portada_guardada = True

                        archivo_pdf.save(ruta_pdf)
                        pdf_guardado = True

                        conexion = mysql.connector.connect(**DB_CONFIG)
                        cursor = conexion.cursor()

                        cursor.execute(
                            """
                            INSERT INTO libros (
                                titulo, autor, categoria, editorial,
                                ano_publicacion, cantidad,
                                imagen_portada, libro, id_usuario
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                titulo,
                                autor,
                                categoria,
                                editorial,
                                ano,
                                cantidad,
                                f"uploads/portadas/{nombre_unico_portada}",
                                nombre_unico_pdf,
                                session["id_usuario"]
                            )
                        )

                        conexion.commit()

                        return redirect(url_for("biblioteca_usuario"))

                    except (mysql.connector.Error, OSError):
                        app.logger.exception("Error al publicar el libro")

                        if conexion is not None and conexion.is_connected():
                            conexion.rollback()

                        mensaje = "No se pudo publicar el libro."

                    finally:
                        if conexion is not None and conexion.is_connected():
                            conexion.close()

                        # Limpiar archivos si el registro falló.
                        if mensaje is not None:
                            if portada_guardada and os.path.exists(ruta_portada):
                                os.remove(ruta_portada)

                            if pdf_guardado and os.path.exists(ruta_pdf):
                                os.remove(ruta_pdf)

    return render_template("publicar_libro.html", mensaje=mensaje, now_year=date.today().year)


@app.route("/libro/<int:id_libro>")
@login_requerido
def descargar_libro(id_libro):
    conexion = None

    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor()

        cursor.execute(
            "SELECT libro FROM libros WHERE id_libro = %s",
            (id_libro,)
        )

        resultado = cursor.fetchone()

    except mysql.connector.Error:
        app.logger.exception("Error al buscar el archivo del libro")
        abort(500)

    finally:
        if conexion is not None and conexion.is_connected():
            conexion.close()

    if not resultado:
        abort(404)

    return send_from_directory(
        LIBROS_FOLDER,
        resultado[0],
        mimetype="application/pdf",
        as_attachment=False,
        download_name="libro.pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)