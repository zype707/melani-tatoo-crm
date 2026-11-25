"""Reglas de la mensajería: quién puede recibir qué y cómo se registra un envío."""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from . import canales, variables
from .models import Canal, MensajePreparado, Plantilla

Estado = MensajePreparado.Estado


class EnvioNoPermitido(Exception):
    pass


def puede_recibir(cliente, promocional: bool) -> tuple[bool, str]:
    if cliente.anonimizado:
        return False, _("Ficha anonimizada.")
    if cliente.contacto_bloqueado:
        return False, _("Pidió no ser contactado.")
    if promocional and not cliente.marketing_consentimiento:
        return False, _("No ha aceptado mensajes promocionales.")
    if not (cliente.telefono or cliente.email or cliente.instagram):
        return False, _("No tiene ningún dato de contacto.")
    return True, ""


def preparar(
    cliente,
    *,
    tipo: str,
    clave: str,
    plantilla: Plantilla | None = None,
    texto: str | None = None,
    fecha: date | None = None,
    caduca_el: date | None = None,
    motivo: str = "",
    promocional: bool | None = None,
    cita=None,
    tatuaje=None,
    campana=None,
    fecha_destacada=None,
) -> tuple[MensajePreparado | None, bool]:
    """Prepara un mensaje si no existe ya uno con la misma clave.

    Devuelve (mensaje, creado). Es idempotente: si la clave existe (aunque el
    mensaje se enviara o descartara) no se vuelve a crear.
    """
    existente = MensajePreparado.objects.filter(clave=clave).first()
    if existente:
        return existente, False
    if plantilla is None and texto is None:
        return None, False
    if plantilla is not None and not plantilla.activa:
        return None, False
    es_promo = promocional if promocional is not None else bool(plantilla and plantilla.es_promocional)
    permitido, _x = puede_recibir(cliente, es_promo)
    if not permitido:
        return None, False
    hoy = timezone.localdate()
    if texto is None:
        contexto = variables.contexto(cliente, cita=cita, tatuaje=tatuaje, fecha_destacada=fecha_destacada, hoy=hoy)
        texto = variables.renderizar(plantilla.cuerpo, contexto)
    try:
        with transaction.atomic():
            mensaje = MensajePreparado.objects.create(
                cliente=cliente,
                tipo=tipo,
                clave=clave[:160],
                texto=texto,
                motivo=motivo[:200],
                plantilla=plantilla,
                es_promocional=es_promo,
                fecha_programada=fecha or hoy,
                caduca_el=caduca_el,
                cita=cita,
                tatuaje=tatuaje,
                campana=campana,
            )
    except IntegrityError:  # otra ejecución lo creó a la vez
        return MensajePreparado.objects.get(clave=clave[:160]), False
    return mensaje, True


def bandeja(hoy: date | None = None):
    return MensajePreparado.objects.para_hoy(hoy).select_related("cliente", "cita", "campana", "tatuaje")


def contar_pendientes_hoy() -> int:
    return MensajePreparado.objects.para_hoy().count()


def acciones(mensaje: MensajePreparado):
    return canales.acciones_para(mensaje.cliente, mensaje.texto)


def guardar_texto(mensaje: MensajePreparado, texto: str) -> None:
    texto = (texto or "").strip()[:4000]
    if texto and texto != mensaje.texto and mensaje.estado == Estado.PENDIENTE:
        mensaje.texto = texto
        mensaje.save(update_fields=["texto"])


def registrar_apertura(mensaje: MensajePreparado, canal: str) -> None:
    if canal in Canal.values:
        mensaje.abierto_en = timezone.now()
        mensaje.canal_usado = canal
        mensaje.save(update_fields=["abierto_en", "canal_usado"])


def marcar_enviado(mensaje: MensajePreparado, canal: str | None = None) -> MensajePreparado:
    permitido, motivo = puede_recibir(mensaje.cliente, mensaje.es_promocional)
    if not permitido:
        raise EnvioNoPermitido(motivo)
    mensaje.estado = Estado.ENVIADO
    mensaje.enviado_en = timezone.now()
    mensaje.canal_usado = canal if canal in Canal.values else (mensaje.canal_usado or Canal.COPIA)
    mensaje.save(update_fields=["estado", "enviado_en", "canal_usado"])
    return mensaje


def deshacer_envio(mensaje: MensajePreparado) -> None:
    mensaje.estado = Estado.PENDIENTE
    mensaje.enviado_en = None
    mensaje.save(update_fields=["estado", "enviado_en"])


def posponer(mensaje: MensajePreparado, dias: int = 1) -> None:
    nueva = timezone.localdate() + timedelta(days=max(1, min(dias, 60)))
    mensaje.fecha_programada = nueva
    mensaje.pospuesto_veces += 1
    if mensaje.caduca_el and mensaje.caduca_el < nueva:
        mensaje.caduca_el = nueva
    mensaje.save(update_fields=["fecha_programada", "pospuesto_veces", "caduca_el"])


def descartar(mensaje: MensajePreparado, motivo: str = "") -> None:
    mensaje.estado = Estado.DESCARTADO
    mensaje.descartado_en = timezone.now()
    mensaje.motivo_descarte = motivo[:120]
    mensaje.save(update_fields=["estado", "descartado_en", "motivo_descarte"])


def descartar_promocionales(cliente) -> int:
    return (
        MensajePreparado.objects.pendientes()
        .filter(cliente=cliente, es_promocional=True)
        .update(estado=Estado.DESCARTADO, descartado_en=timezone.now(), motivo_descarte="Baja de promociones")
    )


def limpiar_pendientes_no_permitidos(hoy: date) -> dict:
    """Caduca lo vencido y descarta lo que ya no se puede enviar."""
    base = MensajePreparado.objects.pendientes()
    caducados = base.filter(caduca_el__lt=hoy).update(estado=Estado.CADUCADO)
    sin_consentimiento = base.filter(es_promocional=True, cliente__marketing_consentimiento=False).update(
        estado=Estado.DESCARTADO, descartado_en=timezone.now(), motivo_descarte="Sin consentimiento"
    )
    bloqueados = base.filter(cliente__contacto_bloqueado=True).update(
        estado=Estado.DESCARTADO, descartado_en=timezone.now(), motivo_descarte="No contactar"
    )
    return {"caducados": caducados, "descartados": sin_consentimiento + bloqueados}
