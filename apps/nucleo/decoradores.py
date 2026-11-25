import functools

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _


def vista_publica(vista):
    """Marca una vista como accesible sin sesión (el middleware la deja pasar)."""
    vista.vista_publica = True
    return vista


def solo_propietaria(vista):
    """Acciones sensibles reservadas a la propietaria (no a una ayudante)."""

    @functools.wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not getattr(request.user, "es_propietaria", False):
            raise PermissionDenied(_("Solo la propietaria del estudio puede hacer esto."))
        return vista(request, *args, **kwargs)

    return envoltura
