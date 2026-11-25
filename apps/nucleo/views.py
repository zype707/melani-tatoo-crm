import hmac
import io
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .archivos import borrar_archivo
from .auditoria import Accion, registrar
from .decoradores import solo_propietaria, vista_publica
from .forms import SECCIONES, ConfirmarCodigoForm, LogoForm, formulario_ajustes
from .limites import superado
from .models import AjustesEstudio, RegistroAuditoria


@vista_publica
@require_GET
def salud(request):
    """Comprobación de salud para Render: la app responde y la BD también."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


@vista_publica
@require_GET
@cache_control(public=True, max_age=3600)
def logo(request):
    """El logotipo aparece en páginas públicas, así que se sirve sin sesión."""
    ajustes = AjustesEstudio.obtener()
    if not ajustes.logo:
        raise Http404
    try:
        return FileResponse(ajustes.logo.open("rb"), content_type="image/png")
    except FileNotFoundError as exc:
        raise Http404 from exc


@vista_publica
def error_csrf(request, reason=""):
    return render(request, "errores/csrf.html", status=403)


@vista_publica
def error_403(request, exception=None):
    return render(request, "errores/403.html", status=403)


@vista_publica
def error_404(request, exception=None):
    return render(request, "errores/404.html", status=404)


@vista_publica
def error_500(request):
    # Sin contexto de petición: si la BD está caída, la página de error no debe consultarla.
    return HttpResponse(render_to_string("errores/500.html"), status=500)


# --- Ajustes del estudio ---------------------------------------------------------------------


def _codigo_valido(request, form) -> bool:
    from apps.cuentas.servicios import dispositivo_totp

    dispositivo = dispositivo_totp(request.user)
    return bool(
        form.is_valid() and dispositivo and dispositivo.verify_token(form.cleaned_data["codigo"].replace(" ", ""))
    )


@solo_propietaria
def ajustes(request):
    seccion = request.GET.get("seccion", "marca")
    if seccion not in SECCIONES and seccion != "datos":
        seccion = "marca"
    instancia = AjustesEstudio.obtener()
    form = None
    if seccion in SECCIONES:
        form = formulario_ajustes(seccion)(request.POST or None, instance=instancia)
    logo_form = LogoForm()
    if request.method == "POST":
        if request.POST.get("accion") == "logo":
            logo_form = LogoForm(request.POST, request.FILES)
            if logo_form.is_valid():
                if logo_form.cleaned_data["quitar"] or logo_form.cleaned_data["logo"]:
                    borrar_archivo(instancia.logo)
                    instancia.logo = logo_form.cleaned_data["logo"] or ""
                    instancia.save(update_fields=["logo", "actualizado_en"])
                messages.success(request, "Logotipo actualizado.")
                return redirect(f"{request.path}?seccion=marca")
        elif form is not None and form.is_valid():
            cambios = form.changed_data
            form.save()
            registrar(request, Accion.AJUSTES, f"Ajustes · {SECCIONES[seccion][0]}", campos=cambios)
            if "texto_consentimiento" in cambios:
                messages.warning(request, "Nuevo texto de consentimiento: las próximas firmas usarán la nueva versión.")
            messages.success(request, "Ajustes guardados.")
            return redirect(f"{request.path}?seccion={seccion}")
    return render(
        request,
        "nucleo/ajustes.html",
        {
            "form": form,
            "logo_form": logo_form,
            "seccion": seccion,
            "secciones": SECCIONES,
            "confirmar": ConfirmarCodigoForm(),
            "copias": _copias(),
            "ajustes_obj": instancia,
        },
    )


def _copias():
    from .exportacion import listar_copias

    return listar_copias()[:10]


@solo_propietaria
@require_POST
def exportar_todo(request):
    from .exportacion import exportar

    form = ConfirmarCodigoForm(request.POST)
    if not _codigo_valido(request, form):
        messages.error(request, "Código incorrecto. La exportación necesita tu código de la app autenticadora.")
        return redirect("/ajustes/?seccion=datos")
    tmp = tempfile.NamedTemporaryFile(prefix="exportacion-", suffix=".zip", delete=False)  # noqa: SIM115
    tmp.close()
    datos = exportar(Path(tmp.name))
    registrar(request, Accion.EXPORTACION, "Exportación completa de datos", **datos)
    respuesta = FileResponse(
        open(tmp.name, "rb"),  # noqa: SIM115 - FileResponse cierra el archivo al terminar
        as_attachment=True,
        filename=f"exportacion-{timezone.localdate():%Y%m%d}.zip",
    )
    respuesta["Cache-Control"] = "private, no-store"
    Path(tmp.name).unlink(missing_ok=True)  # el descriptor abierto mantiene el contenido hasta terminar
    return respuesta


@solo_propietaria
@require_POST
def copias(request):
    form = ConfirmarCodigoForm(request.POST)
    if not _codigo_valido(request, form):
        messages.error(request, "Código incorrecto.")
        return redirect("/ajustes/?seccion=datos")
    if request.POST.get("accion") == "crear":
        from .exportacion import copia_de_seguridad

        destino = copia_de_seguridad()
        registrar(request, Accion.TAREA, f"Copia de seguridad manual {destino.name}")
        messages.success(request, f"Copia creada: {destino.name}")
        return redirect("/ajustes/?seccion=datos")
    nombre = Path(request.POST.get("nombre", "")).name
    ruta = Path(settings.COPIAS_ROOT) / nombre
    if not nombre.startswith("copia-") or not ruta.is_file():
        raise Http404
    registrar(request, Accion.EXPORTACION, f"Descarga de copia {nombre}")
    return FileResponse(open(ruta, "rb"), as_attachment=True, filename=nombre)


@solo_propietaria
def auditoria(request):
    qs = RegistroAuditoria.objects.select_related("usuario")
    accion = request.GET.get("accion", "")
    if accion in RegistroAuditoria.Accion.values:
        qs = qs.filter(accion=accion)
    pagina = Paginator(qs, 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "nucleo/auditoria.html",
        {"pagina": pagina, "accion": accion, "acciones": RegistroAuditoria.Accion.choices},
    )


# --- Tareas internas (cron → web service) ---------------------------------------------------

TAREAS_PERMITIDAS = {"limpiar_archivos", "copia_seguridad"}


@vista_publica
@csrf_exempt
@require_POST
def tarea_interna(request, nombre):
    secreto = settings.TAREAS_SECRETO or ""
    if len(secreto) < 32 or nombre not in TAREAS_PERMITIDAS:
        raise Http404
    if superado("tarea-interna", limite=10, ventana_segundos=3600):
        return JsonResponse({"error": "demasiadas peticiones"}, status=429)
    cabecera = request.headers.get("Authorization", "")
    if not hmac.compare_digest(cabecera.encode(), f"Bearer {secreto}".encode()):
        registrar(request, Accion.TAREA, f"Intento no autorizado: {nombre}")
        return JsonResponse({"error": "no autorizado"}, status=403)
    salida = io.StringIO()
    call_command(nombre, stdout=salida)
    registrar(request, Accion.TAREA, f"Tarea {nombre}")
    return JsonResponse({"tarea": nombre, "salida": salida.getvalue().strip().splitlines()[-5:]})


# --- PWA -------------------------------------------------------------------------------------


@vista_publica
@require_GET
def manifest(request):
    a = AjustesEstudio.obtener()
    datos = {
        "name": a.nombre,
        "short_name": a.nombre[:12],
        "description": "Agenda, clientes y mensajes del estudio",
        "lang": "es",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#062f38",
        "theme_color": "#01161b",
        "icons": [
            {"src": static("img/icono-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icono-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("img/icono-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {"name": "Mensajes de hoy", "url": "/mensajes/"},
            {"name": "Nueva cita", "url": "/agenda/nueva/"},
        ],
    }
    return HttpResponse(json.dumps(datos, ensure_ascii=False), content_type="application/manifest+json")


@vista_publica
@require_GET
def service_worker(request):
    respuesta = render(
        request,
        "nucleo/sw.js",
        {
            "recursos": [
                static(r)
                for r in (
                    "css/app.css",
                    "js/app.js",
                    "js/mensajes.js",
                    "js/dictado.js",
                    "vendor/htmx-2.0.11.min.js",
                    "img/iconos.svg",
                    "img/icono-192.png",
                    "fuentes/archivo-latin-var.woff2",
                    "fuentes/atkinson-hyperlegible-latin-400-normal.woff2",
                    "fuentes/atkinson-hyperlegible-latin-700-normal.woff2",
                )
            ],
            "version": settings.SITE_URL[-6:] + str(len(static("css/app.css"))),
        },
        content_type="application/javascript",
    )
    respuesta["Service-Worker-Allowed"] = "/"
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


@vista_publica
@require_GET
def offline(request):
    return render(request, "nucleo/offline.html")
