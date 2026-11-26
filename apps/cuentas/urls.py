from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("acceso/", views.acceso, name="login"),
    path("salir/", views.salir, name="salir"),
    path("cuenta/", views.cuenta, name="cuenta"),
]
