"""Tokens de páginas públicas: 256 bits aleatorios, con caducidad y revocables."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .models import EnlacePublico

_FORMATO = re.compile(r"^[A-Za-z0-9_-]{43}$")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_enlace(
    proposito: str,
    *,
    objeto_id: int | None = None,
    caduca_en: datetime | None = None,
    dias: int = 30,
) -> tuple[EnlacePublico, str]:
    token = secrets.token_urlsafe(32)  # 43 caracteres, 256 bits
    publico = proposito in (EnlacePublico.Proposito.RESERVA, EnlacePublico.Proposito.CATALOGO)
    enlace = EnlacePublico.objects.create(
        proposito=proposito,
        token_hash=hash_token(token),
        token_visible=token if publico else "",
        objeto_id=objeto_id,
        caduca_en=caduca_en or timezone.now() + timedelta(days=dias),
    )
    return enlace, token


def resolver(proposito: str, token: str, *, contar_uso: bool = True) -> EnlacePublico | None:
    """Devuelve el enlace si el token es válido, vigente y del propósito indicado."""
    if not token or not _FORMATO.match(token):
        return None
    enlace = EnlacePublico.objects.filter(token_hash=hash_token(token), proposito=proposito).first()
    if enlace is None or not enlace.vigente:
        return None
    if contar_uso:
        EnlacePublico.objects.filter(pk=enlace.pk).update(usos=F("usos") + 1, ultimo_uso_en=timezone.now())
    return enlace


def revocar(proposito: str, objeto_id: int | None = None) -> int:
    filtros = {"proposito": proposito, "revocado_en__isnull": True}
    if objeto_id is not None:
        filtros["objeto_id"] = objeto_id
    return EnlacePublico.objects.filter(**filtros).update(revocado_en=timezone.now())


def enlace_estudio_vigente(proposito: str) -> EnlacePublico | None:
    return (
        EnlacePublico.objects.filter(proposito=proposito, revocado_en__isnull=True, caduca_en__gt=timezone.now())
        .exclude(token_visible="")
        .order_by("-creado_en")
        .first()
    )


def url_absoluta(ruta: str) -> str:
    return f"{settings.SITE_URL}{ruta}"
