from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.formulario, name="nuevo"),
    path("enlace/", views.gestionar_enlace, name="enlace"),
    path("<int:pk>/", views.formulario, name="editar"),
    path("<int:pk>/estado/", views.cambiar_estado, name="estado"),
    path("<int:pk>/imagen/", views.imagen, name="imagen"),
    path("<int:pk>/imagen/grande/", views.imagen, {"variante": "grande"}, name="imagen_grande"),
]
