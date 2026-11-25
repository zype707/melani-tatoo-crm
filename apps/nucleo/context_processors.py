from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .models import AjustesEstudio
from .navegacion import contadores


def estudio(request):
    datos = {
        "ajustes": SimpleLazyObject(AjustesEstudio.obtener),
        "SITE_URL": settings.SITE_URL,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        datos["nav"] = SimpleLazyObject(lambda: contadores(request))
        datos["ia_disponible"] = SimpleLazyObject(_ia_disponible)
    return datos


def _ia_disponible():
    from apps.ia.servicios import disponible

    return disponible()
