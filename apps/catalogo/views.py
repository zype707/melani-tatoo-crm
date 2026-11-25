from django.contrib import messages
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from apps.nucleo import tokens
from apps.nucleo.archivos import borrar_archivo, servir
from apps.nucleo.decoradores import vista_publica
from apps.nucleo.limites import limitar
from apps.nucleo.models import AjustesEstudio

from .forms import DisenoForm
from .models import DisenoFlash

Proposito = tokens.EnlacePublico.Proposito


def _url_catalogo():
    enlace = tokens.enlace_estudio_vigente(Proposito.CATALOGO)
    if not enlace:
        return None, ""
    return enlace, tokens.url_absoluta(reverse("flash_publico", args=[enlace.token_visible]))


def lista(request):
    estado = request.GET.get("estado", "")
    qs = DisenoFlash.objects.annotate(n_solicitudes=Count("solicitudes"))
    if estado in DisenoFlash.Estado.values:
        qs = qs.filter(estado=estado)
    enlace, url = _url_catalogo()
    cuentas = {e: DisenoFlash.objects.filter(estado=e).count() for e in DisenoFlash.Estado.values}
    return render(
        request,
        "catalogo/lista.html",
        {
            "disenos": qs,
            "estado": estado,
            "estados": DisenoFlash.Estado.choices,
            "cuentas": cuentas,
            "enlace": enlace,
            "url_publica": url,
            "ajustes": AjustesEstudio.obtener(),
        },
    )


def formulario(request, pk=None):
    diseno = get_object_or_404(DisenoFlash, pk=pk) if pk else None
    form = DisenoForm(request.POST or None, request.FILES or None, instance=diseno)
    if request.method == "POST":
        if diseno and "borrar" in request.POST:
            borrar_archivo(diseno.imagen)
            borrar_archivo(diseno.miniatura)
            diseno.delete()
            messages.success(request, _("Diseño eliminado."))
            return redirect("catalogo:lista")
        if form.is_valid():
            form.save()
            messages.success(request, _("Diseño guardado."))
            return redirect("catalogo:lista")
    return render(request, "catalogo/formulario.html", {"form": form, "diseno": diseno})


@require_POST
def cambiar_estado(request, pk):
    diseno = get_object_or_404(DisenoFlash, pk=pk)
    nuevo = request.POST.get("estado")
    if nuevo in DisenoFlash.Estado.values:
        diseno.estado = nuevo
        diseno.save(update_fields=["estado"])
    if request.headers.get("HX-Request"):
        return render(request, "catalogo/_tarjeta.html", {"d": diseno})
    return redirect("catalogo:lista")


@require_POST
def gestionar_enlace(request):
    ajustes = AjustesEstudio.obtener()
    accion = request.POST.get("accion")
    if accion == "publicar":
        ajustes.flash_publico = True
        ajustes.save(update_fields=["flash_publico", "actualizado_en"])
        if not tokens.enlace_estudio_vigente(Proposito.CATALOGO):
            tokens.crear_enlace(Proposito.CATALOGO, dias=365)
        messages.success(request, _("Catálogo publicado."))
    elif accion == "ocultar":
        ajustes.flash_publico = False
        ajustes.save(update_fields=["flash_publico", "actualizado_en"])
        messages.success(request, _("Catálogo oculto."))
    elif accion == "renovar":
        tokens.revocar(Proposito.CATALOGO)
        tokens.crear_enlace(Proposito.CATALOGO, dias=365)
        messages.success(request, _("Enlace del catálogo renovado."))
    return redirect("catalogo:lista")


def imagen(request, pk, variante="mini"):
    d = get_object_or_404(DisenoFlash, pk=pk)
    return servir(d.miniatura if variante == "mini" else d.imagen)


# --- Público ------------------------------------------------------------------------------------


def _token_valido(token: str) -> bool:
    return bool(
        tokens.resolver(Proposito.CATALOGO, token, contar_uso=False)
        or tokens.resolver(Proposito.RESERVA, token, contar_uso=False)
    )


@vista_publica
@limitar("catalogo", limite=120, ventana_segundos=600, metodos=("GET",))
def publico(request, token):
    ajustes = AjustesEstudio.obtener()
    enlace = tokens.resolver(Proposito.CATALOGO, token)
    if enlace is None or not ajustes.flash_publico:
        return render(request, "publico/enlace_invalido.html", status=404)
    disenos = DisenoFlash.objects.filter(publico=True).exclude(estado=DisenoFlash.Estado.VENDIDO)
    reserva = tokens.enlace_estudio_vigente(Proposito.RESERVA) if ajustes.reservas_activas else None
    return render(request, "publico/flash.html", {"disenos": disenos, "token": token, "reserva": reserva})


@vista_publica
@limitar("catalogo-img", limite=600, ventana_segundos=600, metodos=("GET",))
@cache_control(private=True, max_age=3600)
def imagen_publica(request, token, pk, variante="mini"):
    if not _token_valido(token):
        raise Http404
    d = get_object_or_404(DisenoFlash, pk=pk)
    if not d.visible_al_publico:
        raise Http404
    respuesta = servir(d.miniatura if variante == "mini" else d.imagen)
    respuesta["Cache-Control"] = "private, max-age=3600"
    return respuesta
