from django.urls import path

from . import views_ayuda as views

app_name = "ayuda"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("pista/", views.cerrar_pista, name="pista"),
    path("preferencias/", views.preferencias, name="preferencias"),
    path("paso/", views.marcar_paso, name="paso"),
]
