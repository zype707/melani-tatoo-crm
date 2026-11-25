from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.calendario, name="calendario"),
    path("nueva/", views.nueva, name="nueva"),
    path("cita/<int:pk>/", views.detalle, name="detalle"),
    path("cita/<int:pk>/editar/", views.editar, name="editar"),
    path("cita/<int:pk>/estado/", views.cambiar_estado, name="estado"),
    path("cita/<int:pk>/cambio-atendido/", views.atender_cambio, name="atender_cambio"),
    path("cita/<int:pk>/realizada/", views.cerrar_sesion, name="cerrar_sesion"),
    path("cita/<int:pk>/pagos/", views.pago_nuevo, name="pago_nuevo"),
    path("cita/<int:pk>/enlace/", views.generar_enlace, name="enlace"),
    path("pagos/<int:pk>/devolver/", views.pago_devolver, name="pago_devolver"),
    path("pagos/<int:pk>/borrar/", views.pago_borrar, name="pago_borrar"),
    path("espera/", views.lista_espera, name="lista_espera"),
    path("espera/nueva/", views.espera_formulario, name="espera_nueva"),
    path("espera/<int:pk>/", views.espera_formulario, name="espera_editar"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("configuracion/tipos/nuevo/", views.tipo_formulario, name="tipo_nuevo"),
    path("configuracion/tipos/<int:pk>/", views.tipo_formulario, name="tipo_editar"),
    path("configuracion/bloqueos/nuevo/", views.bloqueo_formulario, name="bloqueo_nuevo"),
    path("configuracion/bloqueos/<int:pk>/borrar/", views.bloqueo_borrar, name="bloqueo_borrar"),
]
