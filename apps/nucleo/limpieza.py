"""Limpieza de datos caducados (solo base de datos; los archivos van aparte)."""

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import EnlacePublico


def limpiar_base_de_datos() -> dict:
    from apps.cuentas.models import IntentoAcceso

    ahora = timezone.now()
    resultado = {
        "enlaces_caducados": EnlacePublico.objects.filter(caduca_en__lt=ahora - timedelta(days=7)).delete()[0],
        "enlaces_revocados": EnlacePublico.objects.filter(revocado_en__lt=ahora - timedelta(days=7)).delete()[0],
        "sesiones": Session.objects.filter(expire_date__lt=ahora).delete()[0],
        "intentos_acceso": IntentoAcceso.objects.filter(creado_en__lt=ahora - timedelta(days=90)).delete()[0],
    }
    return resultado
