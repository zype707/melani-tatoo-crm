"""Bandeja de solicitudes: de la página pública a cliente, tatuaje y cita."""

import hashlib

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.clientes.models import Cliente, FotoTatuaje, OrigenConsentimiento, Tatuaje
from apps.nucleo.archivos import borrar_archivo

from .models import SolicitudReserva


def huella_ip(ip: str | None) -> str:
    if not ip:
        return ""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()


def buscar_cliente(s: SolicitudReserva) -> Cliente | None:
    filtro = Q(telefono=s.telefono) if s.telefono else Q()
    if s.email:
        filtro |= Q(email__iexact=s.email)
    if not filtro:
        return None
    return Cliente.objects.activos().filter(filtro).order_by("creado_en").first()


@transaction.atomic
def vincular_cliente(s: SolicitudReserva, usuario=None) -> Cliente:
    cliente = s.cliente or buscar_cliente(s)
    if cliente is None:
        cliente = Cliente.objects.create(
            nombre=s.nombre,
            apellidos=s.apellidos,
            telefono=s.telefono,
            email=s.email,
            instagram=s.instagram,
            fecha_nacimiento=s.fecha_nacimiento,
            origen=Cliente.Origen.WEB,
        )
    else:
        cambios = []
        for campo in ("email", "instagram", "fecha_nacimiento", "apellidos"):
            if not getattr(cliente, campo) and getattr(s, campo):
                setattr(cliente, campo, getattr(s, campo))
                cambios.append(campo)
        if cambios:
            cliente.save(update_fields=[*cambios, "actualizado_en"])
    if s.acepta_marketing and not cliente.marketing_consentimiento:
        cliente.dar_consentimiento(OrigenConsentimiento.FORMULARIO, usuario, "Casilla del formulario de reserva")
    s.cliente = cliente
    s.save(update_fields=["cliente"])
    return cliente


@transaction.atomic
def crear_tatuaje(s: SolicitudReserva) -> Tatuaje:
    if s.tatuaje_id:
        return s.tatuaje
    cliente = s.cliente or vincular_cliente(s)
    titulo = s.descripcion.strip().split("\n")[0][:60] or f"Proyecto de {s.get_zona_display().lower()}"
    t = Tatuaje.objects.create(
        cliente=cliente,
        titulo=titulo,
        zona=s.zona,
        estilo=s.estilo,
        tamano=s.tamano,
        medidas=s.medidas,
        notas=f"Desde la solicitud del {s.creado_en:%d/%m/%Y}:\n{s.descripcion}",
    )
    for img in s.imagenes.all():
        with img.imagen.open("rb") as f:
            principal = ContentFile(f.read(), name=img.imagen.name.rsplit("/", 1)[-1])
        with img.miniatura.open("rb") as f:
            mini = ContentFile(f.read(), name=img.miniatura.name.rsplit("/", 1)[-1])
        FotoTatuaje.objects.create(tatuaje=t, tipo=FotoTatuaje.Tipo.REFERENCIA, imagen=principal, miniatura=mini)
    s.tatuaje = t
    s.save(update_fields=["tatuaje"])
    return t


def marcar(s: SolicitudReserva, estado: str, motivo: str = "") -> None:
    s.estado = estado
    s.revisada_en = timezone.now()
    if motivo:
        s.motivo_rechazo = motivo[:200]
    s.save(update_fields=["estado", "revisada_en", "motivo_rechazo"])


def purgar(s: SolicitudReserva) -> None:
    """Borra imágenes y datos personales de una solicitud rechazada o spam."""
    for img in s.imagenes.all():
        borrar_archivo(img.imagen)
        borrar_archivo(img.miniatura)
        img.delete()
    s.nombre, s.apellidos, s.telefono, s.email, s.instagram = "Solicitud", "eliminada", "", "", ""
    s.descripcion = "(eliminada)"
    s.fechas_preferidas = s.presupuesto = ""
    s.huella_ip = ""
    s.save()


def purgar_antiguas(dias: int = 30) -> int:
    limite = timezone.now() - timezone.timedelta(days=dias)
    qs = SolicitudReserva.objects.filter(
        estado__in=[SolicitudReserva.Estado.RECHAZADA, SolicitudReserva.Estado.SPAM], revisada_en__lt=limite
    ).exclude(descripcion="(eliminada)")
    n = 0
    for s in qs:
        purgar(s)
        n += 1
    return n
