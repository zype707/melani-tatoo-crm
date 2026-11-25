"""Archivos privados: rutas de subida y entrega autenticada."""

import contextlib
import mimetypes
import os

from django.http import FileResponse, Http404
from django.utils import timezone


def _ruta(carpeta: str, nombre: str) -> str:
    hoy = timezone.localdate()
    return f"privado/{carpeta}/{hoy:%Y/%m}/{os.path.basename(nombre)}"


# Funciones a nivel de módulo (las migraciones necesitan poder importarlas)
def ruta_tatuajes(instancia, nombre):
    return _ruta("tatuajes", nombre)


def ruta_solicitudes(instancia, nombre):
    return _ruta("solicitudes", nombre)


def ruta_consentimientos(instancia, nombre):
    return _ruta("consentimientos", nombre)


def ruta_flash(instancia, nombre):
    return _ruta("flash", nombre)


def servir(archivo, *, descarga: bool = False, nombre: str | None = None) -> FileResponse:
    """Entrega un archivo privado. Solo debe llamarse desde vistas protegidas."""
    if not archivo:
        raise Http404
    try:
        manejador = archivo.open("rb")
    except (FileNotFoundError, ValueError) as exc:
        raise Http404 from exc
    tipo = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
    respuesta = FileResponse(
        manejador,
        content_type=tipo,
        as_attachment=descarga,
        filename=nombre or os.path.basename(archivo.name),
    )
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


def borrar_archivo(campo) -> None:
    """Borra el archivo físico de un FileField (sin guardar el modelo)."""
    if campo and campo.name:
        with contextlib.suppress(OSError):
            campo.storage.delete(campo.name)
