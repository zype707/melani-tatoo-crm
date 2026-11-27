from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("buscar/", views.buscar, name="buscar"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("etiquetas/", views.etiquetas, name="etiquetas"),
    path("importar/", views.importar, name="importar"),
    path("importar/revisar/", views.importar_revisar, name="importar_revisar"),
    path("importar/listo/", views.importar_listo, name="importar_listo"),
    path("importar/plantilla.csv", views.importar_plantilla, name="importar_plantilla"),
    path("importar/errores.csv", views.importar_errores, name="importar_errores"),
    path("tatuajes-de-cliente/", views.tatuajes_de_cliente, name="tatuajes_de_cliente"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/salud/", views.salud, name="salud"),
    path("<int:pk>/marketing/", views.marketing, name="marketing"),
    path("<int:pk>/notas/", views.nota, name="nota"),
    path("notas/<int:pk>/borrar/", views.borrar_nota, name="borrar_nota"),
    path("<int:pk>/tatuajes/nuevo/", views.tatuaje_nuevo, name="tatuaje_nuevo"),
    path("tatuajes/<int:pk>/", views.tatuaje, name="tatuaje"),
    path("tatuajes/<int:pk>/editar/", views.tatuaje_editar, name="tatuaje_editar"),
    path("tatuajes/<int:pk>/fotos/", views.subir_fotos, name="subir_fotos"),
    path("fotos/<int:pk>/", views.foto, name="foto"),
    path("fotos/<int:pk>/mini/", views.foto, {"variante": "mini"}, name="foto_mini"),
    path("fotos/<int:pk>/borrar/", views.borrar_foto, name="borrar_foto"),
    path("<int:pk>/consentimiento/", views.consentimiento, name="consentimiento"),
    path("consentimientos/<int:pk>/pdf/", views.consentimiento_pdf, name="consentimiento_pdf"),
    path("<int:pk>/exportar/", views.exportar_datos, name="exportar"),
    path("<int:pk>/anonimizar/", views.anonimizar, name="anonimizar"),
    path("<int:pk>/eliminar/", views.eliminar, name="eliminar"),
]
