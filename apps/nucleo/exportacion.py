"""Exportación completa y copias de seguridad.

- Exportación: datos de negocio (JSON) + archivos, SIN credenciales (hashes de
  contraseñas). Es lo que la tatuadora descarga para llevarse sus datos.
- Copia de seguridad: todo lo necesario para restaurar (incluye cuentas),
  guardada en el disco persistente con rotación.
"""

import os
import zipfile
from itertools import chain
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.utils import timezone

APPS_NEGOCIO = ["nucleo", "clientes", "agenda", "mensajeria", "finanzas", "catalogo", "ia"]
EXCLUIR_EXPORTACION = {"nucleo.enlacepublico"}
APPS_COPIA = ["cuentas", *APPS_NEGOCIO]

LEEME = """Exportación de {estudio} · {fecha}

datos.json   Todos los registros en formato JSON de Django (clientes, citas, tatuajes,
             mensajes, pagos, gastos, plantillas, consentimientos…).
archivos/    Fotos, imágenes de referencia, firmas y PDFs de consentimiento.

Contiene datos personales y de salud: guárdalo cifrado y no lo compartas.
"""


def _modelos(etiquetas_app, excluir=()):
    for etiqueta in etiquetas_app:
        try:
            config = apps.get_app_config(etiqueta)
        except LookupError:
            continue
        for modelo in config.get_models():
            if modelo._meta.label_lower not in excluir:
                yield modelo


def _serializar(etiquetas_app, excluir=()) -> str:
    objetos = chain.from_iterable(m._default_manager.order_by("pk") for m in _modelos(etiquetas_app, excluir))
    return serializers.serialize("json", objetos, indent=1)


def _archivos():
    raiz = Path(settings.MEDIA_ROOT)
    if not raiz.exists():
        return
    for ruta in raiz.rglob("*"):
        if ruta.is_file():
            yield ruta, ruta.relative_to(raiz).as_posix()


def exportar(destino: Path, incluir_archivos: bool = True) -> dict:
    from .models import AjustesEstudio

    n = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LEEME.txt", LEEME.format(estudio=AjustesEstudio.obtener().nombre, fecha=timezone.now().isoformat()))
        z.writestr("datos.json", _serializar(APPS_NEGOCIO, EXCLUIR_EXPORTACION))
        if incluir_archivos:
            for ruta, relativa in _archivos():
                z.write(ruta, f"archivos/{relativa}")
                n += 1
    return {"archivos": n, "bytes": destino.stat().st_size}


def copia_de_seguridad() -> Path:
    carpeta = Path(settings.COPIAS_ROOT)
    carpeta.mkdir(parents=True, exist_ok=True)
    os.chmod(carpeta, 0o700)
    destino = carpeta / f"copia-{timezone.localtime():%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("datos.json", _serializar(APPS_COPIA))
        for ruta, relativa in _archivos():
            z.write(ruta, f"archivos/{relativa}")
    os.chmod(destino, 0o600)
    copias = sorted(carpeta.glob("copia-*.zip"))
    for vieja in copias[: max(0, len(copias) - settings.COPIAS_A_CONSERVAR)]:
        vieja.unlink(missing_ok=True)
    return destino


def listar_copias() -> list[dict]:
    carpeta = Path(settings.COPIAS_ROOT)
    if not carpeta.exists():
        return []
    return [
        {
            "nombre": p.name,
            "bytes": p.stat().st_size,
            "fecha": timezone.datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.get_current_timezone()),
        }
        for p in sorted(carpeta.glob("copia-*.zip"), reverse=True)
    ]
