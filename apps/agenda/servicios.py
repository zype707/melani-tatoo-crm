from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.nucleo import tokens
from apps.nucleo.templatetags.ui import hora

from .models import Bloqueo, Cita, EntradaListaEspera, EstadoCita, HorarioLaboral, limites_dia


class ConflictoAgenda(Exception):
    pass


# --- Disponibilidad ------------------------------------------------------------------


def conflictos(inicio: datetime, fin: datetime, excluir_id: int | None = None) -> list[str]:
    """Motivos por los que [inicio, fin) no está libre (citas activas y bloqueos)."""
    motivos = []
    for c in Cita.objects.solapadas(inicio, fin, excluir_id).select_related("cliente"):
        motivos.append(f"Se solapa con la cita de {c.cliente.nombre} ({hora(c.inicio)}–{hora(c.fin)}).")
    for b in Bloqueo.objects.filter(inicio__lt=fin, fin__gt=inicio):
        motivos.append(f"Ese hueco está bloqueado: {b}.")
    return motivos


def tramos_del_dia(fecha: date) -> list[tuple[datetime, datetime]]:
    tramos = []
    for h in HorarioLaboral.objects.filter(dia_semana=fecha.weekday()):
        tramos.append(
            (
                timezone.make_aware(datetime.combine(fecha, h.hora_inicio)),
                timezone.make_aware(datetime.combine(fecha, h.hora_fin)),
            )
        )
    return tramos


def fuera_de_horario(inicio: datetime, fin: datetime) -> bool:
    local = timezone.localtime(inicio)
    if timezone.localtime(fin).date() != local.date() and timezone.localtime(fin).time() != time.min:
        return True
    return not any(t0 <= inicio and fin <= t1 for t0, t1 in tramos_del_dia(local.date()))


def huecos_libres(desde: date, dias: int = 7, minimo_minutos: int = 120) -> list[dict]:
    """Huecos libres dentro del horario laboral (descontando citas y bloqueos)."""
    ahora = timezone.now()
    resultado = []
    for i in range(dias):
        dia = desde + timedelta(days=i)
        ocupados = [(c.inicio, c.fin) for c in Cita.objects.activas().del_dia(dia)] + [
            (b.inicio, b.fin)
            for b in Bloqueo.objects.filter(inicio__lt=limites_dia(dia)[1], fin__gt=limites_dia(dia)[0])
        ]
        ocupados.sort()
        for t0, t1 in tramos_del_dia(dia):
            cursor = max(t0, ahora)
            for o0, o1 in ocupados:
                if o1 <= cursor or o0 >= t1:
                    continue
                if o0 > cursor and (o0 - cursor) >= timedelta(minutes=minimo_minutos):
                    resultado.append({"inicio": cursor, "fin": o0})
                cursor = max(cursor, o1)
            if cursor < t1 and (t1 - cursor) >= timedelta(minutes=minimo_minutos):
                resultado.append({"inicio": cursor, "fin": t1})
    for h in resultado:
        h["minutos"] = int((h["fin"] - h["inicio"]).total_seconds() // 60)
    return resultado


# --- Estados ----------------------------------------------------------------------------


@transaction.atomic
def cambiar_estado(cita: Cita, nuevo: str, *, por: str = Cita.CanceladaPor.ESTUDIO, motivo: str = "") -> Cita:
    if nuevo not in EstadoCita.values:
        raise ValueError("Estado desconocido")
    cita.estado = nuevo
    if nuevo == EstadoCita.CANCELADA:
        cita.cancelada_en = timezone.now()
        cita.cancelada_por = por
        cita.motivo_cancelacion = motivo[:200]
    elif nuevo in (EstadoCita.CONFIRMADA, EstadoCita.SOLICITADA):
        cita.cancelada_en = None
        cita.cancelada_por = ""
    if nuevo == EstadoCita.CONFIRMADA and por == Cita.CanceladaPor.CLIENTE:
        cita.confirmada_cliente_en = timezone.now()
    try:
        with transaction.atomic():
            cita.save()
    except IntegrityError as exc:
        raise ConflictoAgenda("Ese hueco ya está ocupado por otra cita.") from exc
    if nuevo == EstadoCita.REALIZADA and cita.tatuaje_id:
        t = cita.tatuaje
        if not t.fecha_inicio:
            t.fecha_inicio = timezone.localtime(cita.inicio).date()
            t.save(update_fields=["fecha_inicio"])
        if cita.tipo.categoria == "retoque" and not t.retoque_hecho:
            t.retoque_hecho = True
            t.save(update_fields=["retoque_hecho"])
    return cita


# --- Lista de espera ------------------------------------------------------------------


def sugerencias_lista_espera(cita: Cita, limite: int = 5):
    """A quién ofrecer el hueco que deja una cita cancelada."""
    local = timezone.localtime(cita.inicio)
    franja = EntradaListaEspera.Franja.MANANA if local.hour < 14 else EntradaListaEspera.Franja.TARDE
    candidatos = (
        EntradaListaEspera.objects.filter(activa=True)
        .exclude(cliente_id=cita.cliente_id)
        .filter(cliente__anonimizado_en__isnull=True)
        .select_related("cliente", "tipo")
    )
    resultado = []
    for e in candidatos:
        if e.dias and local.weekday() not in e.dias:
            continue
        if e.franja not in (EntradaListaEspera.Franja.CUALQUIERA, franja):
            continue
        if e.tipo and e.tipo.duracion_minutos > cita.duracion_minutos:
            continue
        coincide_tipo = e.tipo_id == cita.tipo_id
        resultado.append((not e.prioritaria, not coincide_tipo, e.creado_en, e))
    resultado.sort(key=lambda x: x[:3])
    return [r[-1] for r in resultado[:limite]]


# --- Enlace público ----------------------------------------------------------------------


def enlace_cita(cita: Cita) -> str:
    """Nuevo enlace para que el cliente confirme, cancele o pida cambio (sin cuenta)."""
    _, token = tokens.crear_enlace(
        tokens.EnlacePublico.Proposito.CITA,
        objeto_id=cita.pk,
        caduca_en=max(cita.fin, timezone.now()) + timedelta(days=2),
    )
    return tokens.url_absoluta(reverse("cita_publica", args=[token]))


def semana_de(fecha: date) -> list[date]:
    lunes = fecha - timedelta(days=fecha.weekday())
    return [lunes + timedelta(days=i) for i in range(7)]
