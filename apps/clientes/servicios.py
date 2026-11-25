import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, Max, Min, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Cliente


def normalizar_telefono(texto: str) -> str:
    """Devuelve el teléfono en formato E.164 (+14075550123) o lanza ValidationError."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    try:
        numero = phonenumbers.parse(texto, settings.REGION_TELEFONO)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError(_("Ese teléfono no parece válido.")) from exc
    if not phonenumbers.is_possible_number(numero):
        raise ValidationError(_("Ese teléfono no parece válido. Si es extranjero, añade el prefijo (+34…)."))
    return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)


def duplicados(cliente: Cliente):
    filtro = Q()
    if cliente.telefono:
        filtro |= Q(telefono=cliente.telefono)
    if cliente.email:
        filtro |= Q(email__iexact=cliente.email)
    if not filtro:
        return Cliente.objects.none()
    return Cliente.objects.activos().filter(filtro).exclude(pk=cliente.pk)


def anotar_listado(qs):
    """Añade última visita, próxima cita y gasto sin multiplicar filas."""
    from apps.agenda.models import Cita, EstadoCita
    from apps.finanzas.models import Pago

    ultima = (
        Cita.objects.filter(cliente=OuterRef("pk"), estado=EstadoCita.REALIZADA)
        .order_by("-inicio")
        .values("inicio")[:1]
    )
    proxima = Cita.objects.futuras().filter(cliente=OuterRef("pk")).order_by("inicio").values("inicio")[:1]
    gasto = (
        Pago.objects.filter(cliente=OuterRef("pk"), devuelto=False)
        .values("cliente")
        .annotate(t=Sum("importe"))
        .values("t")[:1]
    )
    return qs.annotate(
        ultima_visita=Subquery(ultima),
        proxima_cita=Subquery(proxima),
        gasto=Coalesce(Subquery(gasto), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2)),
    )


def estadisticas(cliente: Cliente) -> dict:
    from apps.agenda.models import EstadoCita

    citas = cliente.citas.aggregate(
        visitas=Count("pk", filter=Q(estado=EstadoCita.REALIZADA)),
        no_shows=Count("pk", filter=Q(estado=EstadoCita.NO_SHOW)),
        ultima=Max("inicio", filter=Q(estado=EstadoCita.REALIZADA)),
        proxima=Min("inicio", filter=Q(estado__in=["solicitada", "confirmada"], inicio__gte=timezone.now())),
    )
    gasto = cliente.pagos.filter(devuelto=False).aggregate(t=Sum("importe"))["t"] or 0
    return {**citas, "gasto": gasto, "tatuajes": cliente.tatuajes.count()}


def linea_de_tiempo(cliente: Cliente, limite: int = 80) -> list[dict]:
    """Une citas, mensajes, notas, tatuajes, pagos y consentimientos en orden cronológico."""
    eventos: list[dict] = []

    for c in cliente.citas.select_related("tipo").order_by("-inicio")[:limite]:
        eventos.append(
            {
                "fecha": c.inicio,
                "icono": "agenda",
                "titulo": f"{c.tipo.nombre} · {c.get_estado_display()}",
                "detalle": c.descripcion,
                "url": reverse("agenda:detalle", args=[c.pk]),
                "estado": c.estado,
            }
        )
    for n in cliente.notas_cliente.all()[:limite]:
        eventos.append(
            {
                "fecha": n.creado_en,
                "icono": "mic" if n.origen == "dictado" else "editar",
                "titulo": n.get_origen_display(),
                "detalle": n.texto,
                "url": "",
            }
        )
    for t in cliente.tatuajes.all()[:limite]:
        eventos.append(
            {
                "fecha": t.creado_en,
                "icono": "aguja",
                "titulo": _("Tatuaje: %(titulo)s") % {"titulo": t.titulo},
                "detalle": " · ".join(filter(None, [t.get_zona_display(), t.get_estilo_display()])),
                "url": reverse("clientes:tatuaje", args=[t.pk]),
            }
        )
    for p in cliente.pagos.all()[:limite]:
        from apps.nucleo.templatetags.ui import dinero

        eventos.append(
            {
                "fecha": timezone.make_aware(timezone.datetime.combine(p.fecha, timezone.datetime.min.time())),
                "icono": "dinero",
                "titulo": f"{p.get_tipo_display()} {dinero(p.importe)}",
                "detalle": p.get_metodo_display() + (_(" · devuelto") if p.devuelto else ""),
                "url": "",
            }
        )
    for e in cliente.eventos_consentimiento.all()[:limite]:
        eventos.append(
            {
                "fecha": e.creado_en,
                "icono": "escudo",
                "titulo": _("Acepta promociones") if e.tipo == "alta" else _("Baja de promociones"),
                "detalle": e.get_origen_display(),
                "url": "",
            }
        )
    try:
        for m in cliente.mensajes.filter(estado="enviado").order_by("-enviado_en")[:limite]:
            eventos.append(
                {
                    "fecha": m.enviado_en,
                    "icono": "enviar",
                    "titulo": _("Mensaje enviado · %(get_tipo_display)s") % {"get_tipo_display": m.get_tipo_display()},
                    "detalle": m.texto,
                    "url": "",
                    "canal": m.get_canal_usado_display(),
                }
            )
    except AttributeError:
        pass
    try:
        for f in cliente.consentimientos.all()[:limite]:
            eventos.append(
                {
                    "fecha": f.firmado_en,
                    "icono": "firma",
                    "titulo": _("Consentimiento firmado"),
                    "detalle": _("Versión %(version_texto)s") % {"version_texto": f.version_texto},
                    "url": reverse("clientes:consentimiento_pdf", args=[f.pk]),
                }
            )
    except AttributeError:
        pass

    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    return eventos[:limite]
