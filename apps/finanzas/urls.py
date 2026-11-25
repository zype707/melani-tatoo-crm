from django.urls import path

from . import views

app_name = "finanzas"

urlpatterns = [
    path("", views.resumen, name="resumen"),
    path("gastos/nuevo/", views.gasto_formulario, name="gasto_nuevo"),
    path("gastos/<int:pk>/", views.gasto_formulario, name="gasto_editar"),
    path("ingresos/nuevo/", views.pago_formulario, name="pago_nuevo"),
    path("ingresos/<int:pk>/", views.pago_formulario, name="pago_editar"),
    path("exportar/", views.exportar, name="exportar"),
]
