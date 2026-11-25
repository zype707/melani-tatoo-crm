from django.urls import path

from . import views

app_name = "ia"

urlpatterns = [
    path("", views.asistente, name="asistente"),
    path("buscar/", views.buscar, name="buscar"),
    path("redactar/", views.redactar, name="redactar"),
    path("respuesta/", views.respuesta, name="respuesta"),
    path("mensajes/<int:pk>/reescribir/", views.reescribir, name="reescribir"),
    path("solicitudes/<int:pk>/triaje/", views.triaje, name="triaje"),
    path("citas/<int:pk>/resumen/", views.resumen, name="resumen"),
    path("clientes/<int:pk>/retencion/", views.retencion, name="retencion"),
]
