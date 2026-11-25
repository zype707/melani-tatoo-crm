from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("acceso/", views.acceso, name="login"),
    path("acceso/verificar/", views.verificar, name="verificar"),
    path("acceso/autenticadora/", views.configurar_2fa, name="configurar_2fa"),
    path("acceso/codigos/", views.codigos, name="codigos"),
    path("salir/", views.salir, name="salir"),
    path("cuenta/", views.cuenta, name="cuenta"),
]
