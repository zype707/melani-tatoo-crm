"""Generación diaria de la bandeja «Mensajes de hoy».

Cada generador es idempotente: la clave única de MensajePreparado garantiza
que ejecutar el proceso dos veces (o diez) no duplica ningún mensaje. Los
generadores con fecha miran una ventana de 2 días hacia atrás para recuperar
lo que no se preparó si un día el cron no se ejecutó.
"""

import logging
from datetime import date, datetime, time, timedelta
from math import ceil

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.agenda.models import Cita, EstadoCita
from apps.clientes.models import Cliente, Tatuaje
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.templatetags.ui import fecha_corta, hora, relativo

from . import segmentos, servicios
from .models import Campana, Categoria, FechaDestacada, MensajePreparado, PasoCuidado, Plantilla

log = logging.getLogger("estudio.mensajeria")
RECUPERACION_DIAS = 2


def _rango(desde: date, hasta: date):
    """[desde 00:00, hasta+1 00:00) en la zona horaria del estudio."""
    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))
    return inicio, fin


def generar_cumpleanos(hoy: date) -> int:
    plantilla = Plantilla.para(Categoria.CUMPLEANOS)
    if not plantilla:
        return 0
    filtro = Q(fecha_nacimiento__month=hoy.month, fecha_nacimiento__day=hoy.day)
    es_bisiesto = hoy.year % 4 == 0 and (hoy.year % 100 != 0 or hoy.year % 400 == 0)
    if hoy.month == 2 and hoy.day == 28 and not es_bisiesto:
        filtro |= Q(fecha_nacimiento__month=2, fecha_nacimiento__day=29)
    creados = 0
    for c in Cliente.objects.activos().filter(filtro):
        edad = hoy.year - c.fecha_nacimiento.year
        _, nuevo = servicios.preparar(
            c,
            tipo=Categoria.CUMPLEANOS,
            clave=f"cumpleanos:{c.pk}:{hoy.year}",
            plantilla=plantilla,
            fecha=hoy,
            caduca_el=hoy + timedelta(days=2),
            motivo=f"Cumple {edad} años hoy",
        )
        creados += nuevo
    return creados


def generar_recordatorios(hoy: date) -> int:
    plantilla = Plantilla.para(Categoria.RECORDATORIO)
    if not plantilla:
        return 0
    dias = max(1, AjustesEstudio.obtener().recordatorio_dias_antes)
    desde, hasta = _rango(hoy + timedelta(days=1), hoy + timedelta(days=dias))
    creados = 0
    for cita in Cita.objects.pendientes().filter(inicio__gte=desde, inicio__lt=hasta).select_related("cliente", "tipo"):
        local = timezone.localtime(cita.inicio)
        _, nuevo = servicios.preparar(
            cita.cliente,
            tipo=Categoria.RECORDATORIO,
            clave=f"recordatorio:{cita.pk}:{local:%Y%m%d%H%M}",
            plantilla=plantilla,
            fecha=hoy,
            caduca_el=local.date(),
            cita=cita,
            motivo=f"Cita {relativo(cita.inicio)} a las {hora(cita.inicio)}"
            + (" · por confirmar" if cita.estado == EstadoCita.SOLICITADA else ""),
        )
        creados += nuevo
    return creados


def _retoque_innecesario(cita: Cita) -> bool:
    if cita.tipo.categoria == "retoque":
        return True
    t = cita.tatuaje
    if t is None:
        return False
    if t.retoque_hecho:
        return True
    posteriores = Cita.objects.filter(tatuaje=t, inicio__gt=cita.inicio).exclude(
        estado__in=[EstadoCita.CANCELADA, EstadoCita.NO_SHOW]
    )
    return posteriores.exists()  # quedan sesiones o ya hay retoque reservado


def generar_cuidados(hoy: date) -> int:
    """Para cada sesión realizada, prepara el paso de cuidados que toca hoy.

    Si un día no se ejecutó el cron, se recupera el paso pendiente (hasta 2
    días tarde), pero nunca se acumulan pasos atrasados: si ya toca el día 3,
    no se envía también el del día 1.
    """
    pasos = [p for p in PasoCuidado.objects.filter(activo=True).select_related("plantilla") if p.plantilla.activa]
    if not pasos:
        return 0
    max_dias = max(p.dias_despues for p in pasos)
    desde, hasta = _rango(hoy - timedelta(days=max_dias + RECUPERACION_DIAS), hoy)
    citas = (
        Cita.objects.filter(estado=EstadoCita.REALIZADA, inicio__gte=desde, inicio__lt=hasta)
        .filter(tipo__categoria__in=["sesion", "retoque"])
        .select_related("cliente", "tipo", "tatuaje")
    )
    creados = 0
    for cita in citas:
        fecha_sesion = timezone.localtime(cita.inicio).date()
        dias = (hoy - fecha_sesion).days
        tocan = [p for p in pasos if p.dias_despues <= dias <= p.dias_despues + RECUPERACION_DIAS]
        normales = [p for p in tocan if not p.es_oferta_retoque]
        elegidos = [max(normales, key=lambda p: p.dias_despues)] if normales else []
        elegidos += [p for p in tocan if p.es_oferta_retoque and not _retoque_innecesario(cita)]
        for paso in elegidos:
            objetivo = fecha_sesion + timedelta(days=paso.dias_despues)
            tipo = Categoria.RETOQUE if paso.es_oferta_retoque else Categoria.CUIDADO
            _, nuevo = servicios.preparar(
                cita.cliente,
                tipo=tipo,
                clave=f"cuidado:{cita.pk}:{paso.pk}",
                plantilla=paso.plantilla,
                fecha=hoy,
                caduca_el=objetivo + timedelta(days=7 if paso.es_oferta_retoque else RECUPERACION_DIAS),
                cita=cita,
                tatuaje=cita.tatuaje,
                motivo=f"{paso.nombre} tras la sesión del {fecha_corta(cita.inicio)}",
            )
            creados += nuevo
    return creados


def generar_aniversarios(hoy: date) -> int:
    plantilla = Plantilla.para(Categoria.ANIVERSARIO)
    if not plantilla:
        return 0
    filtro = Q(fecha_fin__month=hoy.month, fecha_fin__day=hoy.day, fecha_fin__year__lt=hoy.year) | Q(
        fecha_fin__isnull=True,
        estado=Tatuaje.Estado.TERMINADO,
        fecha_inicio__month=hoy.month,
        fecha_inicio__day=hoy.day,
        fecha_inicio__year__lt=hoy.year,
    )
    creados = 0
    ya = set(
        MensajePreparado.objects.filter(tipo=Categoria.ANIVERSARIO, fecha_programada=hoy).values_list(
            "cliente_id", flat=True
        )
    )
    for t in Tatuaje.objects.filter(filtro, cliente__anonimizado_en__isnull=True).select_related("cliente"):
        if t.cliente_id in ya:
            continue  # un aniversario al día por cliente es suficiente
        anios = hoy.year - t.fecha_aniversario.year
        m, nuevo = servicios.preparar(
            t.cliente,
            tipo=Categoria.ANIVERSARIO,
            clave=f"aniversario:{t.pk}:{hoy.year}",
            plantilla=plantilla,
            fecha=hoy,
            caduca_el=hoy + timedelta(days=3),
            tatuaje=t,
            motivo=f"Hoy hace {anios} año{'s' if anios > 1 else ''} de «{t.titulo}»",
        )
        if m:
            ya.add(t.cliente_id)
        creados += nuevo
    return creados


def generar_reactivaciones(hoy: date) -> int:
    plantilla = Plantilla.para(Categoria.REACTIVACION)
    ajustes = AjustesEstudio.obtener()
    if not plantilla or not ajustes.reactivaciones_por_dia:
        return 0
    # Ya se prepararon las de hoy (no rellenar el cupo en segundas ejecuciones)
    hechas_hoy = MensajePreparado.objects.filter(tipo=Categoria.REACTIVACION, creado_en__date=hoy).count()
    cupo = ajustes.reactivaciones_por_dia - hechas_hoy
    if cupo <= 0:
        return 0
    creados = 0
    candidatos = segmentos.clientes("inactivos").order_by("ultima")
    for c in candidatos:
        if creados >= cupo:
            break
        ultima = c.citas.filter(estado=EstadoCita.REALIZADA).order_by("-inicio").first()
        if ultima is None:
            continue
        _, nuevo = servicios.preparar(
            c,
            tipo=Categoria.REACTIVACION,
            clave=f"reactivacion:{c.pk}:{ultima.pk}",
            plantilla=plantilla,
            fecha=hoy,
            caduca_el=hoy + timedelta(days=7),
            motivo=f"Última visita {relativo(ultima.inicio)}",
        )
        creados += nuevo
    return creados


def lanzar_campana(campana: Campana, hoy: date | None = None) -> int:
    """Crea los mensajes de una campaña repartidos en varios días."""
    hoy = hoy or timezone.localdate()
    inicio = max(campana.fecha_inicio, hoy)
    destinatarios = list(segmentos.clientes(campana.segmento).order_by("pk"))
    if campana.fecha_limite:
        dias = max(1, (campana.fecha_limite - inicio).days + 1)
        por_dia = max(1, ceil(len(destinatarios) / dias))
    else:
        por_dia = max(1, campana.por_dia)
    tipo = Categoria.FECHA_DESTACADA if campana.fecha_destacada_id else Categoria.CAMPANA
    creados = 0
    for i, cliente in enumerate(destinatarios):
        fecha = inicio + timedelta(days=i // por_dia)
        caduca = campana.fecha_limite + timedelta(days=1) if campana.fecha_limite else fecha + timedelta(days=5)
        _, nuevo = servicios.preparar(
            cliente,
            tipo=tipo,
            clave=f"campana:{campana.pk}:{cliente.pk}",
            plantilla=campana.plantilla,
            fecha=fecha,
            caduca_el=caduca,
            promocional=True,
            campana=campana,
            fecha_destacada=campana.fecha_destacada,
            motivo=campana.nombre,
        )
        creados += nuevo
    campana.estado = Campana.Estado.ACTIVA
    campana.total = campana.mensajes.count()
    campana.save(update_fields=["estado", "total"])
    return creados


def generar_fechas_destacadas(hoy: date) -> int:
    creados = 0
    for fd in FechaDestacada.objects.filter(activa=True, generar_campana=True, plantilla__isnull=False):
        fecha = fd.proxima(hoy)
        if not fecha or not (fecha - timedelta(days=max(1, fd.dias_ventana) - 1) <= hoy <= fecha):
            continue
        campana, nueva = Campana.objects.get_or_create(
            fecha_destacada=fd,
            anio=fecha.year if fd.regla != fd.Regla.VIERNES13 else fecha.year * 100 + fecha.month,
            defaults={
                "nombre": f"{fd.nombre} {fecha.year}",
                "plantilla": fd.plantilla,
                "segmento": fd.segmento,
                "fecha_inicio": hoy,
                "fecha_limite": fecha,
            },
        )
        if nueva:
            creados += lanzar_campana(campana, hoy)
    return creados


def cerrar_campanas(hoy: date) -> int:
    cerradas = 0
    for c in Campana.objects.filter(estado=Campana.Estado.ACTIVA):
        if not c.mensajes.filter(estado=MensajePreparado.Estado.PENDIENTE).exists():
            c.estado = Campana.Estado.COMPLETADA
            c.save(update_fields=["estado"])
            cerradas += 1
    return cerradas


GENERADORES = {
    "recordatorios": generar_recordatorios,
    "cuidados": generar_cuidados,
    "cumpleanos": generar_cumpleanos,
    "aniversarios": generar_aniversarios,
    "fechas_destacadas": generar_fechas_destacadas,
    "reactivaciones": generar_reactivaciones,
}


def ejecutar_diario(hoy: date | None = None) -> dict:
    """Prepara la bandeja del día. Seguro de ejecutar varias veces."""
    hoy = hoy or timezone.localdate()
    resultado = servicios.limpiar_pendientes_no_permitidos(hoy)
    for nombre, generador in GENERADORES.items():
        try:
            with transaction.atomic():
                resultado[nombre] = generador(hoy)
        except Exception:  # un generador roto no debe impedir el resto
            log.exception("Falló el generador %s", nombre)
            resultado[nombre] = "error"
    resultado["campanas_cerradas"] = cerrar_campanas(hoy)
    return resultado
