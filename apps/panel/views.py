from django.shortcuts import render

from .servicios import datos_panel


def inicio(request):
    return render(request, "panel/inicio.html", datos_panel())
