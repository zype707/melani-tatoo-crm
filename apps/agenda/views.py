import calendar as cal
from datetime import date, datetime, timedelta
from math import ceil

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente, NotaCliente
from apps.finanzas.models import Pago
from apps.nucleo import tokens
from apps.nucleo.decoradores import vista_publica
from apps.nucleo.limites import limitar
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.red import es_htmx

from . import servicios
from .forms import (
    BloqueoForm,
    CancelarClienteForm,
    CancelarForm,
    CerrarSesionForm,
    CitaForm,
    HorarioForm,
    ListaEsperaForm,
    PagoForm,
    ReprogramarClienteForm,
    TipoCitaForm,
)
from .models import (
    Bloqueo,
    Cita,
    EntradaListaEspera,
    EstadoCita,
    HorarioLaboral,
    SolicitudReserva,
    TipoCita,
    limites_dia,
)

VISTAS = {"dia": "Día", "semana": "Semana", "mes": "Mes", "lista": "Lista"}
MIN_FRANJA = 30


# --- Calendario ---------------------------------------------------------------------------


def _mover(fecha: date, vista: str, pasos: int) -> date:
    if vista == "dia":
        return fecha + timedelta(days=pasos)
    if vista == "semana":
        return fecha + timedelta(days=7 * pasos)
    if vista == "mes":
        mes = fecha.month - 1 + pasos
        anio = fecha.year + mes // 12
        mes = mes % 12 + 1
        return date(anio, mes, min(fecha.day, cal.monthrange(anio, mes)[1]))
    return fecha + timedelta(days=30 * pasos)


def _rejilla(dias: list[date]) -> dict:
    """Datos para la vista de día/semana: filas de 30 min y posición de cada bloque."""
    desde, _ = limites_dia(dias[0])
    _, hasta = limites_dia(dias[-1])
    citas = list(
        Cita.objects.entre(desde, hasta).exclude(estado=EstadoCita.CANCELADA).select_related("cliente", "tipo")
    )
    bloqueos = list(Bloqueo.objects.filter(inicio__lt=hasta, fin__gt=desde))
    horario = list(HorarioLaboral.objects.all())

    hora_ini = min([h.hora_inicio.hour for h in horario] or [10])
    hora_fin = max([h.hora_fin.hour + (1 if h.hora_fin.minute else 0) for h in horario] or [20])
    for c in citas:
        li, lf = timezone.localtime(c.inicio), timezone.localtime(c.fin)
        hora_ini = min(hora_ini, li.hour)
        hora_fin = max(hora_fin, lf.hour + (1 if lf.minute else 0) if lf.date() == li.date() else 24)
    hora_ini, hora_fin = max(0, hora_ini), min(24, max(hora_fin, hora_ini + 1))
    filas = (hora_fin - hora_ini) * 60 // MIN_FRANJA
    ahora = timezone.localtime()

    def posicion(inicio, fin, dia):
        base = timezone.make_aware(datetime.combine(dia, datetime.min.time())) + timedelta(hours=hora_ini)
        tope = base + timedelta(hours=hora_fin - hora_ini)
        inicio, fin = max(inicio, base), min(fin, tope)
        if fin <= inicio:
            return None
        fila = int((inicio - base).total_seconds() // 60 // MIN_FRANJA) + 1
        span = max(1, ceil((fin - inicio).total_seconds() / 60 / MIN_FRANJA))
        return fila, span

    columnas = []
    for dia in dias:
        tramos = [(h.hora_inicio, h.hora_fin) for h in horario if h.dia_semana == dia.weekday()]
        franjas = []
        for i in range(filas):
            minutos = hora_ini * 60 + i * MIN_FRANJA
            momento = datetime.combine(dia, datetime.min.time()) + timedelta(minutes=minutos)
            laboral = any(t0 <= momento.time() < t1 for t0, t1 in tramos)
            franjas.append({"fila": i + 1, "momento": momento, "laboral": laboral})
        eventos = []
        for c in citas:
            if timezone.localtime(c.inicio).date() != dia:
                continue
            pos = posicion(c.inicio, c.fin, dia)
            if pos:
                eventos.append({"cita": c, "fila": pos[0], "span": pos[1]})
        capas = []
        for b in bloqueos:
            pos = posicion(b.inicio, b.fin, dia)
            if pos:
                capas.append({"bloqueo": b, "fila": pos[0], "span": pos[1]})
        linea_ahora = None
        if dia == ahora.date() and hora_ini <= ahora.hour < hora_fin:
            linea_ahora = round(((ahora.hour - hora_ini) * 60 + ahora.minute) / ((hora_fin - hora_ini) * 60) * 100, 2)
        columnas.append(
            {
                "dia": dia,
                "hoy": dia == ahora.date(),
                "franjas": franjas,
                "eventos": eventos,
                "bloqueos": capas,
                "ahora": linea_ahora,
                "laborable": bool(tramos),
            }
        )
    horas = [{"fila": (h - hora_ini) * 2 + 1, "hora": h} for h in range(hora_ini, hora_fin)]
    return {"columnas": columnas, "filas": filas, "horas": horas}


def _mes(fecha: date) -> dict:
    primero = fecha.replace(day=1)
    inicio = primero - timedelta(days=primero.weekday())
    dias = [inicio + timedelta(days=i) for i in range(42)]
    desde, _ = limites_dia(dias[0])
    _, hasta = limites_dia(dias[-1])
    citas = Cita.objects.entre(desde, hasta).exclude(estado=EstadoCita.CANCELADA).select_related("cliente", "tipo")
    por_dia: dict[date, list] = {}
    for c in citas:
        por_dia.setdefault(timezone.localtime(c.inicio).date(), []).append(c)
    bloqueados = set()
    for b in Bloqueo.objects.filter(inicio__lt=hasta, fin__gt=desde):
        d = max(timezone.localtime(b.inicio).date(), dias[0])
        while d <= min(timezone.localtime(b.fin - timedelta(seconds=1)).date(), dias[-1]):
            bloqueados.add(d)
            d += timedelta(days=1)
    hoy = timezone.localdate()
    semanas = []
    for s in range(6):
        semana = []
        for d in dias[s * 7 : s * 7 + 7]:
            lista = por_dia.get(d, [])
            semana.append(
                {
                    "dia": d,
                    "citas": lista[:3],
                    "mas": max(0, len(lista) - 3),
                    "total": len(lista),
                    "otro_mes": d.month != fecha.month,
                    "hoy": d == hoy,
                    "bloqueado": d in bloqueados,
                }
            )
        semanas.append(semana)
    return {"semanas": semanas}


def _lista(fecha: date, estado: str) -> dict:
    desde, _ = limites_dia(fecha)
    qs = Cita.objects.filter(inicio__gte=desde, inicio__lt=desde + timedelta(days=30)).select_related("cliente", "tipo")
    if estado in EstadoCita.values:
        qs = qs.filter(estado=estado)
    else:
        qs = qs.exclude(estado=EstadoCita.CANCELADA)
    grupos: dict[date, list] = {}
    for c in qs.order_by("inicio"):
        grupos.setdefault(timezone.localtime(c.inicio).date(), []).append(c)
    return {"grupos": sorted(grupos.items()), "estado": estado}


def calendario(request):
    vista = request.GET.get("vista") or request.session.get("vista_agenda", "semana")
    if vista not in VISTAS:
        vista = "semana"
    request.session["vista_agenda"] = vista
    fecha = parse_date(request.GET.get("fecha", "")) or timezone.localdate()
    contexto = {
        "vista": vista,
        "vistas": VISTAS,
        "fecha": fecha,
        "anterior": _mover(fecha, vista, -1),
        "siguiente": _mover(fecha, vista, 1),
        "hoy": timezone.localdate(),
        "tipos": TipoCita.objects.filter(activo=True),
        "por_confirmar": Cita.objects.futuras().filter(estado=EstadoCita.SOLICITADA).count(),
        "cambios_pedidos": Cita.objects.futuras()
        .exclude(reprogramacion_pedida="")
        .filter(reprogramacion_atendida=False)
        .count(),
    }
    if vista in ("dia", "semana"):
        dias = [fecha] if vista == "dia" else servicios.semana_de(fecha)
        contexto.update(_rejilla(dias), dias=dias)
    elif vista == "mes":
        contexto.update(_mes(fecha))
    else:
        contexto.update(_lista(fecha, request.GET.get("estado", "")))
    plantilla = "agenda/calendario.html"
    if es_htmx(request) and request.headers.get("HX-Target") == "calendario":
        plantilla += "#calendario"
    return render(request, plantilla, contexto)


# --- Citas ----------------------------------------------------------------------------------


def _guardar_cita(request, form, cita=None):
    try:
        with transaction.atomic():
            return form.save()
    except IntegrityError:
        form.add_error(None, "Ese hueco acaba de ocuparse con otra cita. Elige otra hora.")
        return None


def nueva(request):
    inicial = {"estado": EstadoCita.CONFIRMADA}
    tipo = TipoCita.objects.filter(activo=True).first()
    if tipo:
        inicial.update(tipo=tipo, duracion=tipo.duracion_minutos)
    momento = parse_datetime(request.GET.get("inicio", ""))
    if momento:
        inicial.update(fecha=momento.date(), hora=momento.time())
    elif parse_date(request.GET.get("fecha", "")):
        inicial["fecha"] = parse_date(request.GET["fecha"])
    cliente = None
    if request.GET.get("cliente", "").isdigit():
        cliente = Cliente.objects.activos().filter(pk=request.GET["cliente"]).first()
        if cliente:
            inicial["cliente"] = cliente
    if request.GET.get("tatuaje", "").isdigit():
        inicial["tatuaje"] = request.GET["tatuaje"]
    form = CitaForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        cita = _guardar_cita(request, form)
        if cita:
            if request.GET.get("solicitud", "").isdigit():
                SolicitudReserva.objects.filter(pk=request.GET["solicitud"]).update(
                    cita=cita, estado=SolicitudReserva.Estado.CONVERTIDA, revisada_en=timezone.now()
                )
            messages.success(request, f"Cita guardada para {cita.cliente.nombre}.")
            return redirect("agenda:detalle", cita.pk)
    if request.method == "POST" and form.data.get("cliente", "").isdigit():
        cliente = Cliente.objects.filter(pk=form.data["cliente"]).first()
    return render(request, "agenda/cita_formulario.html", {"form": form, "cliente": cliente})


def editar(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("cliente"), pk=pk)
    form = CitaForm(request.POST or None, instance=cita, initial={"cliente": cita.cliente})
    if request.method == "POST" and form.is_valid() and _guardar_cita(request, form, cita):
        messages.success(request, "Cita actualizada.")
        return redirect("agenda:detalle", cita.pk)
    return render(request, "agenda/cita_formulario.html", {"form": form, "cita": cita, "cliente": cita.cliente})


def detalle(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("cliente", "tipo", "tatuaje"), pk=pk)
    ajustes = AjustesEstudio.obtener()
    contexto = {
        "cita": cita,
        "pagos": cita.pagos.all(),
        "pago_form": PagoForm(initial={"tipo": Pago.Tipo.SENA, "importe": cita.tipo.deposito_sugerido}),
        "cancelar_form": CancelarForm(),
        "sugerencias": servicios.sugerencias_lista_espera(cita) if cita.estado == EstadoCita.CANCELADA else [],
        "salud": getattr(cita.cliente, "salud", None),
        "es_menor": cita.cliente.es_menor(ajustes.edad_minima),
    }
    return render(request, "agenda/cita_detalle.html", contexto)


@require_POST
def cambiar_estado(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    nuevo = request.POST.get("estado", "")
    if nuevo == EstadoCita.REALIZADA:
        return redirect("agenda:cerrar_sesion", cita.pk)
    form = CancelarForm(request.POST) if nuevo == EstadoCita.CANCELADA else None
    try:
        if form is not None and form.is_valid():
            servicios.cambiar_estado(
                cita, nuevo, por=form.cleaned_data["cancelada_por"], motivo=form.cleaned_data["motivo"]
            )
        elif nuevo in EstadoCita.values:
            servicios.cambiar_estado(cita, nuevo)
        messages.success(request, f"Cita marcada como «{cita.get_estado_display().lower()}».")
    except servicios.ConflictoAgenda as exc:
        messages.error(request, str(exc))
    if request.POST.get("atendida"):
        cita.reprogramacion_atendida = True
        cita.save(update_fields=["reprogramacion_atendida"])
    return redirect("agenda:detalle", cita.pk)


@require_POST
def atender_cambio(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    cita.reprogramacion_atendida = True
    cita.save(update_fields=["reprogramacion_atendida"])
    messages.success(request, "Petición de cambio marcada como atendida.")
    return redirect("agenda:detalle", cita.pk)


def cerrar_sesion(request, pk):
    """Marcar como realizada: cobro, notas y estado del tatuaje en un solo paso."""
    cita = get_object_or_404(Cita.objects.select_related("cliente", "tatuaje", "tipo"), pk=pk)
    pendiente = (cita.precio or 0) - cita.pagado
    form = CerrarSesionForm(
        request.POST or None,
        initial={"importe": pendiente if pendiente > 0 else None, "notas_sesion": cita.notas_sesion},
    )
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            with transaction.atomic():
                cita.notas_sesion = datos["notas_sesion"]
                cita.save(update_fields=["notas_sesion"])
                servicios.cambiar_estado(cita, EstadoCita.REALIZADA)
                if datos.get("importe"):
                    Pago.objects.create(
                        cliente=cita.cliente,
                        cita=cita,
                        tatuaje=cita.tatuaje,
                        importe=datos["importe"],
                        metodo=datos["metodo"],
                        tipo=Pago.Tipo.SESION,
                    )
                if datos["notas_sesion"].strip():
                    NotaCliente.objects.create(
                        cliente=cita.cliente,
                        cita=cita,
                        texto=datos["notas_sesion"],
                        origen=NotaCliente.Origen.SESION,
                        autor=request.user,
                    )
                if datos.get("terminado") and cita.tatuaje:
                    t = cita.tatuaje
                    t.estado = t.Estado.TERMINADO
                    t.fecha_fin = timezone.localtime(cita.inicio).date()
                    t.save(update_fields=["estado", "fecha_fin"])
        except servicios.ConflictoAgenda as exc:
            messages.error(request, str(exc))
            return redirect("agenda:detalle", cita.pk)
        messages.success(request, "Sesión cerrada. Los cuidados posteriores se prepararán solos.")
        if cita.tatuaje:
            return redirect(reverse("clientes:tatuaje", args=[cita.tatuaje.pk]) + "#fotos")
        return redirect("agenda:detalle", cita.pk)
    return render(request, "agenda/cerrar_sesion.html", {"cita": cita, "form": form, "pendiente": pendiente})


@require_POST
def pago_nuevo(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("cliente"), pk=pk)
    form = PagoForm(request.POST)
    if form.is_valid():
        pago = form.save(commit=False)
        pago.cita, pago.cliente, pago.tatuaje = cita, cita.cliente, cita.tatuaje
        pago.save()
        messages.success(request, "Pago registrado.")
    else:
        messages.error(request, "Revisa el importe y la fecha del pago.")
    return redirect(reverse("agenda:detalle", args=[cita.pk]) + "#pagos")


@require_POST
def pago_devolver(request, pk):
    pago = get_object_or_404(Pago, pk=pk)
    pago.devuelto = not pago.devuelto
    pago.devuelto_en = timezone.localdate() if pago.devuelto else None
    pago.save(update_fields=["devuelto", "devuelto_en"])
    messages.success(request, "Pago marcado como devuelto." if pago.devuelto else "Devolución anulada.")
    return redirect(request.POST.get("volver") or reverse("agenda:detalle", args=[pago.cita_id]))


@require_POST
def pago_borrar(request, pk):
    pago = get_object_or_404(Pago, pk=pk)
    volver = request.POST.get("volver") or (reverse("agenda:detalle", args=[pago.cita_id]) if pago.cita_id else "/")
    pago.delete()
    messages.success(request, "Pago eliminado.")
    return redirect(volver)


@require_POST
def generar_enlace(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    url = servicios.enlace_cita(cita)
    return render(request, "agenda/_enlace.html", {"url": url, "cita": cita})


# --- Lista de espera ----------------------------------------------------------------------------


def lista_espera(request):
    entradas = EntradaListaEspera.objects.filter(activa=True).select_related("cliente", "tipo")
    return render(request, "agenda/lista_espera.html", {"entradas": entradas})


def espera_formulario(request, pk=None):
    entrada = get_object_or_404(EntradaListaEspera, pk=pk) if pk else None
    inicial = {}
    if not entrada and request.GET.get("cliente", "").isdigit():
        inicial["cliente"] = request.GET["cliente"]
    form = ListaEsperaForm(request.POST or None, instance=entrada, initial=inicial)
    if request.method == "POST":
        if entrada and "quitar" in request.POST:
            entrada.activa = False
            entrada.save(update_fields=["activa"])
            messages.success(request, "Quitado de la lista de espera.")
            return redirect("agenda:lista_espera")
        if form.is_valid():
            form.save()
            messages.success(request, "Lista de espera actualizada.")
            return redirect("agenda:lista_espera")
    cliente_id = form["cliente"].value()
    cliente = Cliente.objects.filter(pk=cliente_id).first() if str(cliente_id or "").isdigit() else None
    return render(request, "agenda/espera_formulario.html", {"form": form, "entrada": entrada, "cliente": cliente})


# --- Configuración de la agenda ----------------------------------------------------------------


def configuracion(request):
    form = HorarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Horario guardado.")
        return redirect("agenda:configuracion")
    ahora = timezone.now()
    return render(
        request,
        "agenda/configuracion.html",
        {
            "horario_form": form,
            "tipos": TipoCita.objects.all(),
            "bloqueos": Bloqueo.objects.filter(fin__gte=ahora),
        },
    )


def tipo_formulario(request, pk=None):
    tipo = get_object_or_404(TipoCita, pk=pk) if pk else None
    form = TipoCitaForm(request.POST or None, instance=tipo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tipo de cita guardado.")
        return redirect("agenda:configuracion")
    return render(request, "agenda/tipo_formulario.html", {"form": form, "tipo": tipo})


def bloqueo_formulario(request):
    inicial = {}
    if parse_date(request.GET.get("fecha", "")):
        inicial["desde_fecha"] = inicial["hasta_fecha"] = parse_date(request.GET["fecha"])
    form = BloqueoForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Bloqueo añadido a la agenda.")
        return redirect("agenda:configuracion")
    return render(request, "agenda/bloqueo_formulario.html", {"form": form})


@require_POST
def bloqueo_borrar(request, pk):
    get_object_or_404(Bloqueo, pk=pk).delete()
    messages.success(request, "Bloqueo eliminado.")
    return redirect("agenda:configuracion")


# --- Página pública de la cita (sin cuenta) -----------------------------------------------------


@vista_publica
@limitar("cita_publica", limite=20, ventana_segundos=3600)
def publica(request, token):
    enlace = tokens.resolver(tokens.EnlacePublico.Proposito.CITA, token, contar_uso=request.method == "GET")
    cita = Cita.objects.select_related("cliente", "tipo").filter(pk=enlace.objeto_id).first() if enlace else None
    if cita is None:
        return render(request, "publico/enlace_invalido.html", status=404)

    reprogramar_form = ReprogramarClienteForm(request.POST if request.POST.get("accion") == "reprogramar" else None)
    cancelar_form = CancelarClienteForm(request.POST if request.POST.get("accion") == "cancelar" else None)
    hecho = ""
    if request.method == "POST" and cita.puede_gestionarla_cliente:
        accion = request.POST.get("accion")
        if accion == "confirmar":
            servicios.cambiar_estado(cita, EstadoCita.CONFIRMADA, por=Cita.CanceladaPor.CLIENTE)
            hecho = "confirmada"
        elif accion == "cancelar" and cancelar_form.is_valid():
            servicios.cambiar_estado(
                cita, EstadoCita.CANCELADA, por=Cita.CanceladaPor.CLIENTE, motivo=cancelar_form.cleaned_data["motivo"]
            )
            hecho = "cancelada"
        elif accion == "reprogramar" and reprogramar_form.is_valid():
            cita.reprogramacion_pedida = reprogramar_form.cleaned_data["texto"]
            cita.reprogramacion_pedida_en = timezone.now()
            cita.reprogramacion_atendida = False
            cita.save(update_fields=["reprogramacion_pedida", "reprogramacion_pedida_en", "reprogramacion_atendida"])
            hecho = "reprogramar"
        if hecho:
            return redirect(f"{request.path}?hecho={hecho}")
    return render(
        request,
        "publico/cita.html",
        {
            "cita": cita,
            "reprogramar_form": reprogramar_form,
            "cancelar_form": cancelar_form,
            "hecho": request.GET.get("hecho", ""),
        },
    )
