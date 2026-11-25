from django.urls import path

from . import views_solicitudes as views

app_name = "solicitudes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("enlace/", views.gestionar_enlace, name="enlace"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/aceptar/", views.aprobar, name="aprobar"),
    path("<int:pk>/cita/", views.convertir, name="convertir"),
    path("<int:pk>/rechazar/", views.rechazar, name="rechazar"),
    path("imagenes/<int:pk>/", views.imagen, name="imagen"),
    path("imagenes/<int:pk>/mini/", views.imagen, {"variante": "mini"}, name="imagen_mini"),
]
