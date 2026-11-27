from django.urls import include, path

from apps.agenda import views as agenda
from apps.agenda import views_solicitudes as reservas
from apps.catalogo import views as catalogo
from apps.nucleo import views as nucleo

urlpatterns = [
    path("", include("apps.panel.urls")),
    path("", include("apps.cuentas.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("agenda/", include("apps.agenda.urls")),
    path("mensajes/", include("apps.mensajeria.urls")),
    path("solicitudes/", include("apps.agenda.urls_solicitudes")),
    path("finanzas/", include("apps.finanzas.urls")),
    path("flash/", include("apps.catalogo.urls")),
    path("asistente/", include("apps.ia.urls")),
    path("ajustes/", include("apps.nucleo.urls")),
    path("ayuda/", include("apps.nucleo.urls_ayuda")),
    # Páginas públicas (protegidas con token)
    path("c/<str:token>/", agenda.publica, name="cita_publica"),
    path("r/<str:token>/", reservas.reserva_publica, name="reserva_publica"),
    path("r/<str:token>/gracias/", reservas.reserva_gracias, name="reserva_gracias"),
    path("f/<str:token>/", catalogo.publico, name="flash_publico"),
    path("f/<str:token>/img/<int:pk>/", catalogo.imagen_publica, name="flash_publico_imagen"),
    path(
        "f/<str:token>/img/<int:pk>/grande/",
        catalogo.imagen_publica,
        {"variante": "grande"},
        name="flash_publico_grande",
    ),
    # Infraestructura
    path("salud/", nucleo.salud, name="salud"),
    path("idioma/", nucleo.cambiar_idioma, name="cambiar_idioma"),
    path("jsi18n/", nucleo.catalogo_js, name="catalogo_js"),
    path("manifest.webmanifest", nucleo.manifest, name="manifest"),
    path("sw.js", nucleo.service_worker, name="service_worker"),
    path("offline/", nucleo.offline, name="offline"),
    path("interno/tareas/<str:nombre>/", nucleo.tarea_interna, name="tarea_interna"),
    path("marca/logo/", nucleo.logo, name="logo"),
]

handler403 = "apps.nucleo.views.error_403"
handler404 = "apps.nucleo.views.error_404"
handler500 = "apps.nucleo.views.error_500"
