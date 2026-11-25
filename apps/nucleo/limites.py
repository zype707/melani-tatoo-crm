"""Limitación de peticiones con ventana fija sobre la caché de Django.

En producción la caché vive en Postgres (DatabaseCache): sin servicios extra.
"""

import functools
import time

from django.core.cache import cache
from django.shortcuts import render

from .red import ip_cliente


def superado(clave: str, limite: int, ventana_segundos: int) -> bool:
    ventana = int(time.time() // ventana_segundos)
    llave = f"rl:{clave}:{ventana}"
    if cache.add(llave, 1, ventana_segundos + 5):
        return limite < 1
    try:
        n = cache.incr(llave)
    except ValueError:
        cache.set(llave, 1, ventana_segundos + 5)
        n = 1
    return n > limite


def limitar(nombre: str, limite: int, ventana_segundos: int, metodos=("POST",)):
    """Decorador de vista: responde 429 si una IP supera el límite."""

    def decorador(vista):
        @functools.wraps(vista)
        def envoltura(request, *args, **kwargs):
            if request.method in metodos:
                ip = ip_cliente(request) or "sin-ip"
                if superado(f"{nombre}:{ip}", limite, ventana_segundos):
                    return render(request, "errores/429.html", status=429)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
