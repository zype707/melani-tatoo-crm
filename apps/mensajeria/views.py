import json
import uuid
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from apps.agenda.models import Cita, EntradaListaEspera
from apps.clientes.models import Cliente
from apps.nucleo import idioma

from . import canales, generadores, segmentos, servicios, variables
from .forms import CampanaForm, FechaDestacadaForm, MensajeLibreForm, PasoCuidadoForm, PlantillaForm
from .models import ICONOS, Campana, Categoria, FechaDestacada, MensajePreparado, PasoCuidado, Plantilla

Estado = MensajePreparado.Estado


def _contexto_mensaje(m: MensajePreparado) -> dict:
    return {"m": m, "acciones": servicios.acciones(m), "preferido": canales.canal_preferido(m.cliente)}


def _tarjeta(request, m, plantilla="mensajeria/_mensaje.html", aviso=None):
    respuesta = render(request, plantilla, _contexto_mensaje(m))
    if aviso:
        respuesta["HX-Trigger"] = json.dumps({"aviso": {"texto": aviso, "tipo": "success"}, "bandeja-cambio": True})
    return respuesta


def _quitar(aviso: str) -> HttpResponse:
    respuesta = HttpResponse("")
    respuesta["HX-Trigger"] = json.dumps({"aviso": {"texto": aviso, "tipo": "success"}, "bandeja-cambio": True})
    return respuesta


# --- Bandeja «Mensajes de hoy» -------------------------------------------------------------


def bandeja(request):
    hoy = timezone.localdate()
    tipo = request.GET.get("tipo", "")
    pendientes = sorted(servicios.bandeja(hoy), key=lambda m: (m.prioridad, m.fecha_programada, m.pk))
    recuento = {}
    for m in pendientes:
        recuento[m.tipo] = recuento.get(m.tipo, 0) + 1
    if tipo:
        pendientes = [m for m in pendientes if m.tipo == tipo]
    enviados_hoy = MensajePreparado.objects.filter(estado=Estado.ENVIADO, enviado_en__date=hoy).count()
    contexto = {
        "hoy": hoy,
        "mensajes": [_contexto_mensaje(m) for m in pendientes],
        "recuento": [
            (k, Categoria(k).label, ICONOS[k], n)
            for k, n in sorted(recuento.items(), key=lambda x: Categoria.values.index(x[0]))
        ],
        "total": sum(recuento.values()),
        "tipo": tipo,
        "enviados_hoy": enviados_hoy,
        "proximos": MensajePreparado.objects.pendientes().filter(fecha_programada__gt=hoy).count(),
    }
    return render(request, "mensajeria/bandeja.html", contexto)


@require_POST
def generar_ahora(request):
    resultado = generadores.ejecutar_diario()
    nuevos = sum(
        v
        for k, v in resultado.items()
        if isinstance(v, int) and k not in ("caducados", "descartados", "campanas_cerradas")
    )
    messages.success(
        request,
        ngettext(
            "Bandeja actualizada: %(nuevos)s mensaje nuevo.", "Bandeja actualizada: %(nuevos)s mensajes nuevos.", nuevos
        )
        % {"nuevos": nuevos},
    )
    return redirect("mensajeria:bandeja")


def _mensaje(pk):
    return get_object_or_404(MensajePreparado.objects.select_related("cliente", "cita", "campana"), pk=pk)


@require_POST
def guardar_texto(request, pk):
    m = _mensaje(pk)
    servicios.guardar_texto(m, request.POST.get("texto", ""))
    return render(request, "mensajeria/_acciones.html", _contexto_mensaje(m))


@require_POST
def abrir(request, pk):
    """Se llama al pulsar WhatsApp / SMS / Copiar: guarda el texto y pregunta si se envió."""
    m = _mensaje(pk)
    if "texto" in request.POST:
        servicios.guardar_texto(m, request.POST["texto"])
    servicios.registrar_apertura(m, request.POST.get("canal", ""))
    return render(request, "mensajeria/_acciones.html", _contexto_mensaje(m))


@require_POST
def enviado(request, pk):
    m = _mensaje(pk)
    try:
        servicios.marcar_enviado(m, request.POST.get("canal"))
    except servicios.EnvioNoPermitido as exc:
        respuesta = HttpResponse(status=409)
        respuesta["HX-Trigger"] = json.dumps(
            {"aviso": {"texto": _("No se puede enviar: %(exc)s") % {"exc": exc}, "tipo": "error"}}
        )
        if request.headers.get("HX-Request"):
            return respuesta
        messages.error(request, _("No se puede enviar: %(exc)s") % {"exc": exc})
        return redirect("mensajeria:bandeja")
    if not request.headers.get("HX-Request"):
        messages.success(request, _("Mensaje registrado como enviado."))
        return redirect(request.POST.get("volver") or "mensajeria:bandeja")
    return _tarjeta(request, m, aviso=_("Guardado en el historial."))


@require_POST
def deshacer(request, pk):
    m = _mensaje(pk)
    servicios.deshacer_envio(m)
    return _tarjeta(request, m)


@require_POST
def posponer(request, pk):
    m = _mensaje(pk)
    try:
        dias = int(request.POST.get("dias", 1))
    except ValueError:
        dias = 1
    servicios.posponer(m, dias)
    return _quitar(_("Pospuesto hasta el %(fecha)s.") % {"fecha": date_format(m.fecha_programada, _("d/m"))})


@require_POST
def descartar(request, pk):
    servicios.descartar(_mensaje(pk), _("Descartado a mano"))
    return _quitar(_("Mensaje descartado."))


def _texto_hueco(nombre: str) -> str:
    with idioma.contenido():
        return _("¡Hola %(nombre)s! Se ha liberado un hueco. ¿Te interesa?") % {"nombre": nombre}


# --- Mensaje libre y huecos -------------------------------------------------------------------


def nuevo(request):
    inicial = {}
    cliente = None
    if request.GET.get("cliente", "").isdigit():
        cliente = get_object_or_404(Cliente.objects.activos(), pk=request.GET["cliente"])
        inicial["cliente"] = cliente
    form = MensajeLibreForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        c = form.cleaned_data["cliente"]
        m, _x = servicios.preparar(
            c,
            tipo=Categoria.GENERAL,
            clave=f"manual:{uuid.uuid4().hex}",
            texto=form.cleaned_data["texto"],
            plantilla=form.cleaned_data.get("plantilla"),
            promocional=False,
            motivo=_("Mensaje escrito a mano"),
        )
        if m is None:
            _permitido, motivo = servicios.puede_recibir(c, False)
            messages.error(request, motivo or "No se pudo preparar el mensaje.")
        else:
            return redirect("mensajeria:enviar", m.pk)
    if request.method == "POST" and form.data.get("cliente", "").isdigit():
        cliente = Cliente.objects.filter(pk=form.data["cliente"]).first()
    return render(request, "mensajeria/nuevo.html", {"form": form, "cliente": cliente})


def texto_plantilla(request):
    """Rellena el mensaje libre con una plantilla para un cliente (HTMX)."""
    plantilla = Plantilla.objects.filter(pk=request.GET.get("plantilla") or 0).first()
    cliente = Cliente.objects.filter(pk=request.GET.get("cliente") or 0).first()
    if not plantilla:
        return HttpResponse("")
    contexto = variables.contexto(cliente) if cliente else variables.contexto_ejemplo()
    return HttpResponse(variables.renderizar(plantilla.cuerpo, contexto), content_type="text/plain; charset=utf-8")


def enviar(request, pk):
    m = _mensaje(pk)
    return render(request, "mensajeria/enviar.html", _contexto_mensaje(m))


@require_POST
def ofrecer_hueco(request, cita_pk, entrada_pk):
    cita = get_object_or_404(Cita, pk=cita_pk)
    entrada = get_object_or_404(EntradaListaEspera.objects.select_related("cliente"), pk=entrada_pk)
    plantilla = Plantilla.para(Categoria.LISTA_ESPERA)
    m, _x = servicios.preparar(
        entrada.cliente,
        tipo=Categoria.LISTA_ESPERA,
        clave=f"hueco:{cita.pk}:{entrada.pk}",
        plantilla=plantilla,
        texto=None if plantilla else _texto_hueco(entrada.cliente.nombre),
        cita=cita,
        caduca_el=timezone.localtime(cita.inicio).date(),
        motivo=_("Hueco liberado por una cancelación"),
        promocional=False,
    )
    if m is None:
        messages.error(request, _("No se puede contactar a esta persona."))
        return redirect("agenda:detalle", cita.pk)
    entrada.ofrecido_en = timezone.now()
    entrada.save(update_fields=["ofrecido_en"])
    return redirect("mensajeria:enviar", m.pk)


# --- Historial -----------------------------------------------------------------------------------


def historial(request):
    qs = MensajePreparado.objects.filter(estado=Estado.ENVIADO).select_related("cliente").order_by("-enviado_en")
    q = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "")
    canal = request.GET.get("canal", "")
    if q:
        qs = qs.filter(
            Q(cliente__nombre__unaccent__icontains=q)
            | Q(cliente__apellidos__unaccent__icontains=q)
            | Q(texto__icontains=q)
        )
    if tipo in Categoria.values:
        qs = qs.filter(tipo=tipo)
    if canal:
        qs = qs.filter(canal_usado=canal)
    pagina = Paginator(qs, 40).get_page(request.GET.get("pagina"))
    hace30 = timezone.now() - timedelta(days=30)
    por_canal = (
        MensajePreparado.objects.filter(estado=Estado.ENVIADO, enviado_en__gte=hace30)
        .values("canal_usado")
        .annotate(n=Count("pk"))
    )
    return render(
        request,
        "mensajeria/historial.html",
        {
            "pagina": pagina,
            "q": q,
            "tipo": tipo,
            "canal": canal,
            "tipos": Categoria.choices,
            "canales": MensajePreparado._meta.get_field("canal_usado").choices,
            "por_canal": por_canal,
        },
    )


# --- Plantillas ------------------------------------------------------------------------------------


def plantillas(request):
    grupos = {}
    for p in Plantilla.objects.all():
        grupos.setdefault(p.get_categoria_display(), []).append(p)
    return render(request, "mensajeria/plantillas.html", {"grupos": grupos})


def plantilla_formulario(request, pk=None):
    plantilla = get_object_or_404(Plantilla, pk=pk) if pk else None
    inicial = {} if plantilla else {"categoria": request.GET.get("categoria", Categoria.GENERAL)}
    form = PlantillaForm(request.POST or None, instance=plantilla, initial=inicial)
    if request.method == "POST":
        if plantilla and "borrar" in request.POST:
            try:
                plantilla.delete()
                messages.success(request, _("Plantilla eliminada."))
                return redirect("mensajeria:plantillas")
            except ProtectedError:
                messages.error(
                    request, _("Esta plantilla se usa en los cuidados o en una campaña. Desactívala en su lugar.")
                )
        elif form.is_valid():
            form.save()
            messages.success(request, _("Plantilla guardada."))
            return redirect("mensajeria:plantillas")
    cuerpo = form["cuerpo"].value() or ""
    return render(
        request,
        "mensajeria/plantilla_formulario.html",
        {
            "form": form,
            "plantilla": plantilla,
            "variables": variables.VARIABLES,
            "vista_previa": variables.renderizar(cuerpo, variables.contexto_ejemplo()),
        },
    )


@require_POST
def vista_previa(request):
    cuerpo = request.POST.get("cuerpo", "")
    return render(
        request,
        "mensajeria/_vista_previa.html",
        {
            "vista_previa": variables.renderizar(cuerpo, variables.contexto_ejemplo()),
            "desconocidas": variables.desconocidas(cuerpo),
            "caracteres": len(cuerpo),
        },
    )


# --- Cuidados ---------------------------------------------------------------------------------------


def cuidados(request, pk=None):
    paso = get_object_or_404(PasoCuidado, pk=pk) if pk else None
    form = PasoCuidadoForm(request.POST or None, instance=paso)
    if request.method == "POST":
        if paso and "borrar" in request.POST:
            paso.delete()
            messages.success(request, _("Paso eliminado."))
            return redirect("mensajeria:cuidados")
        if form.is_valid():
            form.save()
            messages.success(request, _("Secuencia de cuidados actualizada."))
            return redirect("mensajeria:cuidados")
    return render(
        request,
        "mensajeria/cuidados.html",
        {"pasos": PasoCuidado.objects.select_related("plantilla"), "form": form, "paso": paso},
    )


# --- Fechas destacadas ----------------------------------------------------------------------------


def fechas(request):
    hoy = timezone.localdate()
    filas = []
    for f in FechaDestacada.objects.select_related("plantilla"):
        proxima = f.proxima(hoy)
        filas.append({"fecha": f, "proxima": proxima, "dias": (proxima - hoy).days if proxima else None})
    filas.sort(key=lambda x: (x["proxima"] is None, x["proxima"] or hoy))
    return render(request, "mensajeria/fechas.html", {"filas": filas})


def fecha_formulario(request, pk=None):
    fecha = get_object_or_404(FechaDestacada, pk=pk) if pk else None
    form = FechaDestacadaForm(request.POST or None, instance=fecha)
    if request.method == "POST":
        if fecha and "borrar" in request.POST:
            fecha.delete()
            messages.success(request, _("Fecha eliminada."))
            return redirect("mensajeria:fechas")
        if form.is_valid():
            form.save()
            messages.success(request, _("Fecha guardada."))
            return redirect("mensajeria:fechas")
    return render(request, "mensajeria/fecha_formulario.html", {"form": form, "fecha": fecha})


# --- Campañas -----------------------------------------------------------------------------------------


def campanas(request):
    lista = Campana.objects.select_related("plantilla", "fecha_destacada").annotate(
        enviados=Count("mensajes", filter=Q(mensajes__estado=Estado.ENVIADO)),
        pendientes=Count("mensajes", filter=Q(mensajes__estado=Estado.PENDIENTE)),
    )
    resumen = [{"segmento": s, **segmentos.recuento(s.clave)} for s in segmentos.SEGMENTOS.values()]
    return render(request, "mensajeria/campanas.html", {"campanas": lista, "segmentos": resumen})


def campana_nueva(request):
    form = CampanaForm(request.POST or None, initial={"segmento": request.GET.get("segmento", "marketing")})
    if request.method == "POST" and form.is_valid():
        campana = form.save()
        creados = generadores.lanzar_campana(campana)
        dias = -(-creados // max(1, campana.por_dia)) if creados else 0
        messages.success(
            request,
            ngettext(
                "Campaña lanzada: %(creados)s mensajes repartidos en %(dias)s día.",
                "Campaña lanzada: %(creados)s mensajes repartidos en %(dias)s días.",
                dias,
            )
            % {"creados": creados, "dias": dias},
        )
        return redirect("mensajeria:campana", campana.pk)
    clave = form["segmento"].value() or "marketing"
    return render(request, "mensajeria/campana_nueva.html", {"form": form, "recuento": segmentos.recuento(clave)})


def recuento_segmento(request):
    clave = request.GET.get("segmento", "marketing")
    try:
        por_dia = max(1, int(request.GET.get("por_dia") or 10))
    except ValueError:
        por_dia = 10
    datos = segmentos.recuento(clave) if clave in segmentos.SEGMENTOS else {"total": 0, "con_consentimiento": 0}
    datos["dias"] = -(-datos["con_consentimiento"] // por_dia)
    return render(request, "mensajeria/_recuento.html", {"recuento": datos})


def campana(request, pk):
    c = get_object_or_404(Campana.objects.select_related("plantilla", "fecha_destacada"), pk=pk)
    mensajes = c.mensajes.select_related("cliente").order_by("fecha_programada", "pk")
    por_dia = {}
    for m in mensajes:
        d = por_dia.setdefault(m.fecha_programada, {"total": 0, "enviados": 0})
        d["total"] += 1
        d["enviados"] += m.estado == Estado.ENVIADO
    if request.method == "POST":
        if "cancelar" in request.POST:
            n = c.mensajes.filter(estado=Estado.PENDIENTE).update(
                estado=Estado.DESCARTADO, descartado_en=timezone.now(), motivo_descarte=_("Campaña cancelada")
            )
            c.estado = Campana.Estado.CANCELADA
            c.save(update_fields=["estado"])
            messages.success(request, _("Campaña cancelada. %(n)s mensajes pendientes descartados.") % {"n": n})
        elif "ampliar" in request.POST:
            n = generadores.lanzar_campana(c)
            messages.success(
                request,
                ngettext("%(n)s cliente nuevo añadido.", "%(n)s clientes nuevos añadidos.", n) % {"n": n},
            )
        return redirect("mensajeria:campana", c.pk)
    estados = dict.fromkeys(Estado.values, 0)
    for m in mensajes:
        estados[m.estado] += 1
    return render(
        request,
        "mensajeria/campana.html",
        {
            "campana": c,
            "por_dia": sorted(por_dia.items()),
            "estados": estados,
            "mensajes": mensajes[:200],
            "segmento": segmentos.SEGMENTOS.get(c.segmento),
        },
    )


def enlace_ficha(cliente) -> str:
    return reverse("mensajeria:nuevo") + f"?cliente={cliente.pk}"
