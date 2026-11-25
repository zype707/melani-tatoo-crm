from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente
from apps.mensajeria import canales, variables
from apps.mensajeria import servicios as mensajes
from apps.mensajeria.models import Categoria, Plantilla
from apps.nucleo import tokens
from apps.nucleo.archivos import servir
from apps.nucleo.decoradores import vista_publica
from apps.nucleo.limites import limitar, superado
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.red import ip_cliente

from . import solicitudes
from .forms import RechazoForm, SolicitudForm
from .models import ImagenSolicitud, SolicitudReserva

Estado = SolicitudReserva.Estado
PESTANAS = [
    (Estado.NUEVA, "Nuevas"),
    (Estado.APROBADA, "Aceptadas sin fecha"),
    (Estado.CONVERTIDA, "Con cita"),
    (Estado.RECHAZADA, "Rechazadas"),
]


def _enlace_publico():
    enlace = tokens.enlace_estudio_vigente(tokens.EnlacePublico.Proposito.RESERVA)
    if enlace is None:
        return None, ""
    return enlace, tokens.url_absoluta(reverse("reserva_publica", args=[enlace.token_visible]))


# --- Bandeja privada ------------------------------------------------------------------------


def lista(request):
    estado = request.GET.get("estado", Estado.NUEVA)
    if estado not in Estado.values:
        estado = Estado.NUEVA
    qs = SolicitudReserva.objects.filter(estado=estado).prefetch_related("imagenes")
    cuentas = {e: SolicitudReserva.objects.filter(estado=e).count() for e, _ in PESTANAS}
    enlace, url = _enlace_publico()
    return render(
        request,
        "solicitudes/lista.html",
        {
            "solicitudes": qs[:100],
            "estado": estado,
            "pestanas": [(e, n, cuentas[e]) for e, n in PESTANAS],
            "enlace": enlace,
            "url_publica": url,
            "ajustes": AjustesEstudio.obtener(),
        },
    )


@require_POST
def gestionar_enlace(request):
    ajustes = AjustesEstudio.obtener()
    accion = request.POST.get("accion")
    if accion == "renovar":
        tokens.revocar(tokens.EnlacePublico.Proposito.RESERVA)
        tokens.crear_enlace(tokens.EnlacePublico.Proposito.RESERVA, dias=365)
        messages.success(request, "Enlace renovado. El anterior ya no funciona: actualízalo en tu Instagram.")
    elif accion == "crear":
        tokens.crear_enlace(tokens.EnlacePublico.Proposito.RESERVA, dias=365)
        messages.success(request, "Enlace de reservas creado.")
    elif accion in ("abrir", "cerrar"):
        ajustes.reservas_activas = accion == "abrir"
        ajustes.save(update_fields=["reservas_activas", "actualizado_en"])
        messages.success(
            request, "Reservas abiertas." if ajustes.reservas_activas else "Reservas cerradas temporalmente."
        )
    return redirect("solicitudes:lista")


def detalle(request, pk):
    s = get_object_or_404(SolicitudReserva.objects.prefetch_related("imagenes"), pk=pk)
    if s.estado == Estado.NUEVA and s.revisada_en is None:
        s.revisada_en = timezone.now()
        s.save(update_fields=["revisada_en"])
    existente = s.cliente or solicitudes.buscar_cliente(s)
    respuestas = []
    persona = s.cliente or Cliente(nombre=s.nombre, telefono=s.telefono, canal_preferido="whatsapp")
    for p in Plantilla.objects.filter(categoria=Categoria.SOLICITUD, activa=True):
        texto = variables.renderizar(p.cuerpo, {**variables.contexto(persona), "nombre": s.nombre})
        respuestas.append({"plantilla": p, "texto": texto, "acciones": canales.acciones_para(persona, texto)})
    return render(
        request,
        "solicitudes/detalle.html",
        {
            "s": s,
            "existente": existente,
            "rechazo_form": RechazoForm(),
            "respuestas": respuestas,
            "ia": _ia_disponible(),
        },
    )


def _ia_disponible() -> bool:
    try:
        from apps.ia.servicios import disponible

        return disponible()
    except ImportError:
        return False


@require_POST
def aprobar(request, pk):
    s = get_object_or_404(SolicitudReserva, pk=pk)
    with transaction.atomic():
        cliente = solicitudes.vincular_cliente(s, request.user)
        solicitudes.crear_tatuaje(s)
        solicitudes.marcar(s, Estado.APROBADA)
    plantilla = (
        Plantilla.objects.filter(categoria=Categoria.SOLICITUD, activa=True).order_by("-predeterminada", "pk").first()
    )
    if plantilla:
        m, _ = mensajes.preparar(
            cliente,
            tipo=Categoria.SOLICITUD,
            clave=f"solicitud:{s.pk}:aprobada",
            plantilla=plantilla,
            promocional=False,
            motivo="Solicitud aceptada",
        )
        if m:
            messages.success(request, "Solicitud aceptada. Ficha y proyecto creados. Envíale la respuesta:")
            return redirect("mensajeria:enviar", m.pk)
    messages.success(request, "Solicitud aceptada. Ficha y proyecto creados.")
    return redirect("clientes:ficha", cliente.pk)


@require_POST
def convertir(request, pk):
    s = get_object_or_404(SolicitudReserva, pk=pk)
    with transaction.atomic():
        cliente = solicitudes.vincular_cliente(s, request.user)
        tatuaje = solicitudes.crear_tatuaje(s)
    url = reverse("agenda:nueva") + f"?cliente={cliente.pk}&tatuaje={tatuaje.pk}&solicitud={s.pk}"
    return redirect(url)


@require_POST
def rechazar(request, pk):
    s = get_object_or_404(SolicitudReserva, pk=pk)
    form = RechazoForm(request.POST)
    motivo = form.cleaned_data["motivo"] if form.is_valid() else ""
    if request.POST.get("spam"):
        solicitudes.marcar(s, Estado.SPAM, "Spam")
        solicitudes.purgar(s)
        messages.success(request, "Marcada como spam y eliminada.")
    else:
        solicitudes.marcar(s, Estado.RECHAZADA, motivo)
        messages.success(request, "Solicitud rechazada. Sus datos se borrarán solos en 30 días.")
    return redirect("solicitudes:lista")


def imagen(request, pk, variante="completa"):
    img = get_object_or_404(ImagenSolicitud, pk=pk)
    return servir(img.miniatura if variante == "mini" else img.imagen)


# --- Página pública ---------------------------------------------------------------------------


@vista_publica
@limitar("reserva", limite=5, ventana_segundos=3600)
def reserva_publica(request, token):
    ajustes = AjustesEstudio.obtener()
    enlace = tokens.resolver(tokens.EnlacePublico.Proposito.RESERVA, token, contar_uso=request.method == "GET")
    if enlace is None:
        return render(request, "publico/enlace_invalido.html", status=404)
    if not ajustes.reservas_activas:
        return render(request, "publico/reservas_cerradas.html")

    diseno = None
    if request.GET.get("flash", "").isdigit():
        try:
            from apps.catalogo.models import DisenoFlash

            diseno = DisenoFlash.objects.filter(pk=request.GET["flash"], publico=True, estado="disponible").first()
        except ImportError:
            diseno = None

    if request.method == "POST":
        max_bytes = (settings.SUBIDAS_MAX_IMAGENES * settings.SUBIDAS_MAX_MB + 2) * 1024 * 1024
        if int(request.META.get("CONTENT_LENGTH") or 0) > max_bytes:
            return render(request, "errores/413.html", status=413)
        if superado("reserva-global", limite=150, ventana_segundos=86400):
            return render(request, "errores/429.html", status=429)
        form = SolicitudForm(request.POST, request.FILES, edad_minima=ajustes.edad_minima)
        if form.is_valid():
            with transaction.atomic():
                s = form.save(commit=False)
                s.huella_ip = solicitudes.huella_ip(ip_cliente(request))
                if diseno:
                    s.diseno_flash = diseno
                    s.descripcion = f"[Flash: {diseno.titulo}]\n{s.descripcion}"
                s.save()
                for principal, mini in form.cleaned_data["imagenes"]:
                    ImagenSolicitud.objects.create(solicitud=s, imagen=principal, miniatura=mini)
            return redirect("reserva_gracias", token=token)
    else:
        inicial = {}
        if diseno:
            inicial["descripcion"] = f"Me interesa el flash «{diseno.titulo}»."
        form = SolicitudForm(edad_minima=ajustes.edad_minima, initial=inicial)
    return render(request, "publico/reserva.html", {"form": form, "diseno": diseno, "token": token})


@vista_publica
def reserva_gracias(request, token):
    if tokens.resolver(tokens.EnlacePublico.Proposito.RESERVA, token, contar_uso=False) is None:
        return render(request, "publico/enlace_invalido.html", status=404)
    return render(request, "publico/reserva_gracias.html")
