"""Tutorial «Cómo usar» y preferencias de la ayuda en pantalla."""

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import ayuda
from .red import es_htmx


def _volver(request, defecto: str = "") -> str:
    url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if url and url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure()):
        return url
    return defecto or reverse("ayuda:inicio")


def inicio(request):
    usuario = request.user
    pasos = ayuda.primeros_pasos(usuario)
    visibles = [p for p in ayuda.PANTALLAS if not p.propietaria or usuario.es_propietaria]
    pantallas = [{"p": p, "botones": p.botones_para(usuario)} for p in visibles]
    propios = [c for c in ayuda.CAPITULOS if not c.propietaria or usuario.es_propietaria]
    capitulos = [
        {
            "c": c,
            "numero": i,
            "pasos": c.pasos_para(usuario),
            "pantallas": [p for p in visibles if p.clave in c.pantallas],
        }
        for i, c in enumerate(propios, start=1)
    ]
    return render(
        request,
        "nucleo/ayuda.html",
        {
            "pasos": pasos,
            "hechos": sum(p.hecho for p in pasos),
            "capitulos": capitulos,
            "pantallas": pantallas,
            "preguntas": ayuda.PREGUNTAS,
            "glosario": ayuda.GLOSARIO,
            "atajos": ayuda.ATAJOS,
        },
    )


@require_POST
def cerrar_pista(request):
    """«Entendido» en la pista de una pantalla (o en la lista de primeros pasos)."""
    clave = request.POST.get("clave", "")[:40]
    if clave and (ayuda.pantalla(clave) or clave == ayuda.PISTA_PRIMEROS_PASOS):
        request.user.cerrar_ayuda(clave)
    if es_htmx(request):
        return HttpResponse("")
    return redirect(_volver(request))


@require_POST
def preferencias(request):
    """Mostrar u ocultar todas las pistas. Al volver a mostrarlas, reaparecen también las ya cerradas."""
    usuario = request.user
    mostrar = request.POST.get("mostrar") == "1"
    usuario.ayudas_visibles = mostrar
    if mostrar:
        usuario.ayudas_cerradas = [c for c in (usuario.ayudas_cerradas or []) if c.startswith("paso:")]
    usuario.save(update_fields=["ayudas_visibles", "ayudas_cerradas"])
    if es_htmx(request):
        respuesta = HttpResponse("")
        respuesta["HX-Refresh"] = "true"
        return respuesta
    return redirect(_volver(request))


@require_POST
def marcar_paso(request):
    """Marca (o desmarca) a mano un paso de «Primeros pasos» que la app no puede detectar sola."""
    clave = request.POST.get("paso", "")
    if clave in ayuda.CLAVES_PASOS:
        if request.POST.get("hecho") == "1":
            request.user.cerrar_ayuda(f"paso:{clave}")
        else:
            request.user.abrir_ayuda(f"paso:{clave}")
    return redirect(_volver(request, reverse("ayuda:inicio") + "#primeros-pasos"))
