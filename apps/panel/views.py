from django.shortcuts import render

from apps.nucleo.ayuda import PISTA_PRIMEROS_PASOS, primeros_pasos

from .servicios import datos_panel


def inicio(request):
    contexto = datos_panel()
    usuario = request.user
    if usuario.ayudas_visibles and not usuario.ayuda_cerrada(PISTA_PRIMEROS_PASOS):
        pasos = primeros_pasos(usuario)
        pendientes = [p for p in pasos if not p.hecho]
        if pendientes:
            contexto["primeros_pasos"] = {
                "pasos": pendientes[:3],
                "hechos": len(pasos) - len(pendientes),
                "total": len(pasos),
            }
    return render(request, "panel/inicio.html", contexto)
