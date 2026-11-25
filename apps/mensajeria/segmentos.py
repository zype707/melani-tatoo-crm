"""Segmentos automáticos de clientes (calculados al vuelo, no se guardan)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Exists, Max, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy

from apps.clientes.models import Cliente
from apps.nucleo.models import AjustesEstudio


@dataclass(frozen=True)
class Segmento:
    clave: str
    nombre: str
    descripcion: str
    consulta: Callable


def _con_futura():
    from apps.agenda.models import Cita

    return Exists(Cita.objects.futuras().filter(cliente=OuterRef("pk")))


def _ultima_visita():
    from apps.agenda.models import EstadoCita

    return Max("citas__inicio", filter=Q(citas__estado=EstadoCita.REALIZADA))


def inactivos(ajustes=None):
    ajustes = ajustes or AjustesEstudio.obtener()
    limite = timezone.now() - timedelta(days=round(30.44 * ajustes.meses_inactividad))
    return (
        Cliente.objects.activos()
        .annotate(ultima=_ultima_visita(), futura=_con_futura())
        .filter(ultima__lt=limite, futura=False)
    )


def en_riesgo(ajustes=None):
    """Clientes que solían volver (2+ visitas) y llevan tiempo sin hacerlo."""
    from apps.agenda.models import EstadoCita

    return (
        inactivos(ajustes)
        .annotate(visitas=Count("citas", filter=Q(citas__estado=EstadoCita.REALIZADA), distinct=True))
        .filter(visitas__gte=2)
    )


def proyectos_a_medias(ajustes=None):
    return (
        Cliente.objects.activos()
        .filter(tatuajes__estado="en_proceso")
        .annotate(futura=_con_futura())
        .filter(futura=False)
        .distinct()
    )


def vip(ajustes=None):
    from apps.finanzas.models import Pago

    ajustes = ajustes or AjustesEstudio.obtener()
    gasto = (
        Pago.objects.filter(cliente=OuterRef("pk"), devuelto=False)
        .values("cliente")
        .annotate(t=Sum("importe"))
        .values("t")
    )
    return (
        Cliente.objects.activos()
        .annotate(gasto=Subquery(gasto[:1]))
        .filter(Q(etiquetas__nombre__iexact="vip") | Q(gasto__gte=ajustes.umbral_vip))
        .distinct()
    )


def nuevos_del_mes(ajustes=None):
    hoy = timezone.localdate()
    return Cliente.objects.activos().filter(creado_en__year=hoy.year, creado_en__month=hoy.month)


def cumplen_este_mes(ajustes=None):
    return Cliente.objects.activos().filter(fecha_nacimiento__month=timezone.localdate().month)


def todos(ajustes=None):
    return Cliente.objects.activos()


SEGMENTOS: dict[str, Segmento] = {
    s.clave: s
    for s in (
        Segmento(
            "marketing",
            gettext_lazy("Todos los que aceptan promociones"),
            gettext_lazy("Toda tu base con consentimiento."),
            todos,
        ),
        Segmento(
            "inactivos",
            gettext_lazy("No vuelven hace tiempo"),
            gettext_lazy("Sin visitas en los últimos meses y sin cita."),
            inactivos,
        ),
        Segmento(
            "proyectos",
            gettext_lazy("Proyectos a medias"),
            gettext_lazy("Tatuaje en proceso y ninguna cita próxima."),
            proyectos_a_medias,
        ),
        Segmento("vip", gettext_lazy("VIP"), gettext_lazy("Etiqueta VIP o gasto acumulado alto."), vip),
        Segmento("nuevos", gettext_lazy("Nuevos del mes"), gettext_lazy("Fichas creadas este mes."), nuevos_del_mes),
        Segmento(
            "cumple_mes",
            gettext_lazy("Cumplen años este mes"),
            gettext_lazy("Para una promo de cumpleaños."),
            cumplen_este_mes,
        ),
    )
}
OPCIONES = [(s.clave, s.nombre) for s in SEGMENTOS.values()]


def clientes(clave: str, *, solo_marketing: bool = True):
    segmento = SEGMENTOS.get(clave) or SEGMENTOS["marketing"]
    qs = segmento.consulta()
    if solo_marketing:
        qs = qs.filter(marketing_consentimiento=True, contacto_bloqueado=False)
    return qs


def recuento(clave: str) -> dict:
    total = SEGMENTOS[clave].consulta().count() if clave in SEGMENTOS else 0
    return {"total": total, "con_consentimiento": clientes(clave).count() if clave in SEGMENTOS else 0}
