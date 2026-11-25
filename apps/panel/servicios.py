"""Métricas del panel de control."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.agenda.models import Cita, EstadoCita, SolicitudReserva, limites_dia
from apps.agenda.servicios import huecos_libres, semana_de
from apps.clientes.models import Cliente
from apps.finanzas import servicios as finanzas
from apps.mensajeria import segmentos
from apps.mensajeria.models import FechaDestacada
from apps.mensajeria.servicios import contar_pendientes_hoy
from apps.nucleo import graficos


def tasa_no_show(dias: int = 90) -> dict:
    desde = timezone.now() - timedelta(days=dias)
    datos = Cita.objects.filter(inicio__gte=desde, inicio__lt=timezone.now()).aggregate(
        realizadas=Count("pk", filter=Q(estado=EstadoCita.REALIZADA)),
        no_show=Count("pk", filter=Q(estado=EstadoCita.NO_SHOW)),
    )
    total = datos["realizadas"] + datos["no_show"]
    return {**datos, "tasa": (datos["no_show"] / total) if total else None}


def tasa_retorno() -> dict:
    """De quienes ya se tatuaron con ella, cuántos han vuelto (2+ visitas)."""
    conteo = (
        Cliente.objects.activos()
        .annotate(visitas=Count("citas", filter=Q(citas__estado=EstadoCita.REALIZADA)))
        .filter(visitas__gte=1)
        .aggregate(total=Count("pk"), vuelven=Count("pk", filter=Q(visitas__gte=2)))
    )
    total = conteo["total"]
    return {**conteo, "tasa": (conteo["vuelven"] / total) if total else None}


def proximos_cumpleanos(dias: int = 14) -> list[dict]:
    hoy = timezone.localdate()
    resultado = []
    for c in (
        Cliente.objects.activos().exclude(fecha_nacimiento__isnull=True).only("nombre", "apellidos", "fecha_nacimiento")
    ):
        cumple = c.cumple_en(hoy.year)
        if cumple < hoy:
            cumple = c.cumple_en(hoy.year + 1)
        faltan = (cumple - hoy).days
        if faltan <= dias:
            resultado.append(
                {"cliente": c, "fecha": cumple, "faltan": faltan, "edad": cumple.year - c.fecha_nacimiento.year}
            )
    return sorted(resultado, key=lambda x: x["faltan"])[:8]


def proxima_fecha_destacada():
    hoy = timezone.localdate()
    proximas = [(f.proxima(hoy), f) for f in FechaDestacada.objects.filter(activa=True)]
    proximas = [p for p in proximas if p[0]]
    return min(proximas, key=lambda p: p[0]) if proximas else None


def datos_panel() -> dict:
    hoy = timezone.localdate()
    inicio_hoy, fin_hoy = limites_dia(hoy)
    semana = semana_de(hoy)
    inicio_sem, _x = limites_dia(semana[0])
    _x, fin_sem = limites_dia(semana[-1])

    citas_hoy = Cita.objects.del_dia(hoy).exclude(estado=EstadoCita.CANCELADA).select_related("cliente", "tipo")
    citas_semana = Cita.objects.entre(inicio_sem, fin_sem).activas()
    minutos_semana = sum(c.duracion_minutos for c in citas_semana)

    # Ingresos del mes en curso frente al mismo tramo del mes anterior
    inicio_mes = hoy.replace(day=1)
    ingresos_mes = finanzas.ingresos(inicio_mes, hoy)
    mes_ant = finanzas.mes_anterior(hoy)
    _x, fin_mes_ant = finanzas.limites_mes(mes_ant.year, mes_ant.month)
    tramo_ant = mes_ant.replace(day=min(hoy.day, fin_mes_ant.day))
    ingresos_ant = finanzas.ingresos(mes_ant, tramo_ant)
    variacion = float((ingresos_mes - ingresos_ant) / ingresos_ant) if ingresos_ant else None

    serie = finanzas.serie_mensual(hoy, 6)
    grafico = graficos.barras(
        [s["etiqueta"] for s in serie],
        [{"nombre": _("Ingresos"), "valores": [s["ingresos"] for s in serie], "clase": "serie-a"}],
        ancho=520,
        alto=200,
        resaltar=len(serie) - 1,
    )

    avisos = list(
        Cita.objects.filter(
            Q(
                estado=EstadoCita.CANCELADA,
                cancelada_por="cliente",
                cancelada_en__gte=timezone.now() - timedelta(days=7),
                inicio__gte=timezone.now(),
            )
            | Q(inicio__gte=timezone.now(), reprogramacion_atendida=False) & ~Q(reprogramacion_pedida="")
        ).select_related("cliente")[:6]
    )
    en_riesgo = list(segmentos.en_riesgo().order_by("-visitas", "ultima")[:5])

    return {
        "hoy": hoy,
        "citas_hoy": citas_hoy,
        "siguiente": citas_hoy.filter(inicio__gte=timezone.now(), estado__in=["solicitada", "confirmada"]).first(),
        "citas_semana": citas_semana.count(),
        "horas_semana": round(minutos_semana / 60, 1),
        "por_confirmar": Cita.objects.futuras().filter(estado=EstadoCita.SOLICITADA).count(),
        "solicitudes": SolicitudReserva.objects.filter(estado=SolicitudReserva.Estado.NUEVA).count(),
        "mensajes": contar_pendientes_hoy(),
        "ingresos_mes": ingresos_mes,
        "ingresos_ant": ingresos_ant,
        "variacion": variacion,
        "grafico": grafico,
        "no_show": tasa_no_show(),
        "retorno": tasa_retorno(),
        "en_riesgo": en_riesgo,
        "cumpleanos": proximos_cumpleanos(),
        "huecos": huecos_libres(hoy, dias=7, minimo_minutos=120)[:6],
        "avisos": avisos,
        "fecha_destacada": proxima_fecha_destacada(),
        "clientes_total": Cliente.objects.activos().count(),
        "inicio_hoy": inicio_hoy,
        "fin_hoy": fin_hoy,
    }
