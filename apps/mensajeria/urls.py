from django.urls import path

from . import views

app_name = "mensajeria"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("generar/", views.generar_ahora, name="generar"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("texto-plantilla/", views.texto_plantilla, name="texto_plantilla"),
    path("historial/", views.historial, name="historial"),
    path("<int:pk>/", views.enviar, name="enviar"),
    path("<int:pk>/texto/", views.guardar_texto, name="texto"),
    path("<int:pk>/abrir/", views.abrir, name="abrir"),
    path("<int:pk>/enviado/", views.enviado, name="enviado"),
    path("<int:pk>/deshacer/", views.deshacer, name="deshacer"),
    path("<int:pk>/posponer/", views.posponer, name="posponer"),
    path("<int:pk>/descartar/", views.descartar, name="descartar"),
    path("hueco/<int:cita_pk>/<int:entrada_pk>/", views.ofrecer_hueco, name="ofrecer_hueco"),
    path("plantillas/", views.plantillas, name="plantillas"),
    path("plantillas/nueva/", views.plantilla_formulario, name="plantilla_nueva"),
    path("plantillas/<int:pk>/", views.plantilla_formulario, name="plantilla_editar"),
    path("plantillas/vista-previa/", views.vista_previa, name="vista_previa"),
    path("cuidados/", views.cuidados, name="cuidados"),
    path("cuidados/<int:pk>/", views.cuidados, name="cuidado_editar"),
    path("fechas/", views.fechas, name="fechas"),
    path("fechas/nueva/", views.fecha_formulario, name="fecha_nueva"),
    path("fechas/<int:pk>/", views.fecha_formulario, name="fecha_editar"),
    path("campanas/", views.campanas, name="campanas"),
    path("campanas/nueva/", views.campana_nueva, name="campana_nueva"),
    path("campanas/recuento/", views.recuento_segmento, name="recuento"),
    path("campanas/<int:pk>/", views.campana, name="campana"),
]
