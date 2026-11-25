from django.urls import path

from . import views

app_name = "nucleo"

urlpatterns = [
    path("", views.ajustes, name="ajustes"),
    path("exportar/", views.exportar_todo, name="exportar"),
    path("copias/", views.copias, name="copias"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
