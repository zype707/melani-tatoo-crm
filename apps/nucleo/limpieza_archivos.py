"""Limpieza de archivos (se ejecuta en el web service, que es quien tiene el disco)."""

import time
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils import timezone


def archivos_referenciados() -> set[str]:
    nombres: set[str] = set()
    for modelo in apps.get_models():
        campos = [f.name for f in modelo._meta.get_fields() if isinstance(f, models.FileField)]
        for campo in campos:
            nombres.update(n for n in modelo._default_manager.exclude(**{campo: ""}).values_list(campo, flat=True) if n)
    return nombres


def borrar_huerfanos(antiguedad_horas: int = 24, simular: bool = False) -> int:
    raiz = Path(settings.MEDIA_ROOT)
    if not raiz.exists():
        return 0
    usados = archivos_referenciados()
    limite = time.time() - antiguedad_horas * 3600
    borrados = 0
    for ruta in raiz.rglob("*"):
        if not ruta.is_file():
            continue
        relativa = ruta.relative_to(raiz).as_posix()
        if relativa not in usados and ruta.stat().st_mtime < limite:
            if not simular:
                ruta.unlink(missing_ok=True)
            borrados += 1
    return borrados


def caducar_consentimientos() -> int:
    """Borra consentimientos de fichas anonimizadas cuyo plazo legal ya pasó."""
    from apps.clientes.models import ConsentimientoInformado
    from apps.nucleo.archivos import borrar_archivo

    n = 0
    for c in ConsentimientoInformado.objects.filter(
        cliente__anonimizado_en__isnull=False, conservar_hasta__lt=timezone.localdate()
    ):
        borrar_archivo(c.pdf)
        borrar_archivo(c.firma)
        c.delete()
        n += 1
    return n


def limpiar_todo() -> dict:
    from apps.agenda.solicitudes import purgar_antiguas

    return {
        "solicitudes_purgadas": purgar_antiguas(30),
        "consentimientos_caducados": caducar_consentimientos(),
        "archivos_huerfanos": borrar_huerfanos(),
    }
