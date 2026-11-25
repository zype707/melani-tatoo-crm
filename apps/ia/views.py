from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.agenda.models import Cita, SolicitudReserva
from apps.clientes.models import Cliente
from apps.mensajeria.models import MensajePreparado
from apps.mensajeria.servicios import guardar_texto
from apps.nucleo.limites import superado

from . import busqueda, servicios
from .proveedor import ErrorIA


def _error(request, exc: ErrorIA):
    return render(request, "ia/_error.html", {"mensaje": exc.mensaje}, status=200)


def _limitado(request) -> bool:
    return superado(f"ia:{request.user.pk}", limite=20, ventana_segundos=60)


def asistente(request):
    q = request.GET.get("q", "").strip()
    contexto = {
        "estado": servicios.estado(),
        "disponible": servicios.disponible(),
        "q": q,
        "clientes_recientes": Cliente.objects.activos().order_by("-actualizado_en")[:60],
    }
    if q:
        contexto.update(_buscar(request, q))
    return render(request, "ia/asistente.html", contexto)


def _buscar(request, q: str) -> dict:
    origen, aviso = "local", ""
    if servicios.disponible() and request.GET.get("modo") != "local":
        try:
            filtros = servicios.interpretar_busqueda(q, request.user)
            origen = "ia"
        except ErrorIA as exc:
            filtros, aviso = (
                busqueda.interpretar_local(q),
                _("%(mensaje)s Uso la búsqueda básica.") % {"mensaje": exc.mensaje},
            )
    else:
        filtros = busqueda.interpretar_local(q)
    qs, limpios = busqueda.aplicar(filtros)
    pagina = Paginator(qs.prefetch_related("etiquetas"), 40).get_page(request.GET.get("pagina"))
    return {"resultados": pagina, "filtros": busqueda.describir(limpios), "origen": origen, "aviso": aviso}


def buscar(request):
    q = request.GET.get("q", "").strip()
    return render(request, "ia/_resultados.html", {"q": q, **(_buscar(request, q) if q else {})})


@require_POST
def redactar(request):
    """Rellena el cuadro de texto del mensaje libre con un borrador de la IA."""
    cliente = Cliente.objects.activos().filter(pk=request.POST.get("cliente") or 0).first()
    texto_actual = request.POST.get("texto", "")
    if cliente is None:
        return render(
            request, "ia/_textarea.html", {"texto": texto_actual, "error": _("Elige primero a quién va el mensaje.")}
        )
    if _limitado(request):
        return render(
            request, "ia/_textarea.html", {"texto": texto_actual, "error": _("Demasiadas peticiones seguidas.")}
        )
    try:
        texto = servicios.redactar_mensaje(
            cliente,
            request.POST.get("objetivo") or _("mensaje personal"),
            request.POST.get("indicaciones", ""),
            texto_actual,
            request.user,
        )
    except ErrorIA as exc:
        return render(request, "ia/_textarea.html", {"texto": texto_actual, "error": exc.mensaje})
    return render(request, "ia/_textarea.html", {"texto": texto})


@require_POST
def reescribir(request, pk):
    """Reescribe un mensaje de la bandeja con la voz de la tatuadora."""
    m = get_object_or_404(MensajePreparado.objects.select_related("cliente"), pk=pk)
    from apps.mensajeria.views import _contexto_mensaje

    error = ""
    if _limitado(request):
        error = _("Demasiadas peticiones seguidas.")
    else:
        try:
            nuevo = servicios.redactar_mensaje(
                m.cliente,
                m.get_tipo_display() + (f" ({m.motivo})" if m.motivo else ""),
                request.POST.get("indicaciones", ""),
                m.texto,
                request.user,
            )
            guardar_texto(m, nuevo)
        except ErrorIA as exc:
            error = exc.mensaje
    return render(request, "mensajeria/_mensaje.html", {**_contexto_mensaje(m), "error_ia": error})


@require_POST
def triaje(request, pk):
    s = get_object_or_404(SolicitudReserva, pk=pk)
    if _limitado(request):
        return _error(request, ErrorIA(_("Demasiadas peticiones seguidas.")))
    try:
        servicios.triaje_solicitud(s, request.user)
    except ErrorIA as exc:
        return _error(request, exc)
    return render(request, "solicitudes/_triaje.html", {"s": s, "ia": True})


@require_POST
def resumen(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("cliente", "tipo", "tatuaje"), pk=pk)
    if _limitado(request):
        return _error(request, ErrorIA(_("Demasiadas peticiones seguidas.")))
    try:
        texto = servicios.resumen_cita(cita, request.user)
    except ErrorIA as exc:
        return _error(request, exc)
    return render(request, "ia/_texto.html", {"texto": texto, "titulo": _("Resumen para la cita")})


@require_POST
def retencion(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    if _limitado(request):
        return _error(request, ErrorIA(_("Demasiadas peticiones seguidas.")))
    try:
        datos = servicios.sugerencias_retencion(cliente, request.user)
    except ErrorIA as exc:
        return _error(request, exc)
    return render(request, "ia/_retencion.html", {"datos": datos, "cliente": cliente})


@require_POST
def respuesta(request):
    texto = request.POST.get("recibido", "").strip()
    cliente = Cliente.objects.activos().filter(pk=request.POST.get("cliente") or 0).first()
    if not texto:
        return _error(request, ErrorIA(_("Pega primero el mensaje que has recibido.")))
    if _limitado(request):
        return _error(request, ErrorIA(_("Demasiadas peticiones seguidas.")))
    try:
        propuesta = servicios.respuesta_sugerida(texto, cliente, request.POST.get("indicaciones", ""), request.user)
    except ErrorIA as exc:
        return _error(request, exc)
    acciones = []
    if cliente:
        from apps.mensajeria.canales import acciones_para

        acciones = acciones_para(cliente, propuesta)
    return render(request, "ia/_respuesta.html", {"texto": propuesta, "acciones": acciones, "cliente": cliente})
