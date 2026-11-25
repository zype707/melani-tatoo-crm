from django.contrib.auth.backends import ModelBackend

from .permitidos import esta_permitido


class BackendCorreosPermitidos(ModelBackend):
    """ModelBackend que solo reconoce cuentas cuyo email está en CORREOS_PERMITIDOS.

    ``user_can_authenticate`` se usa tanto al autenticar como en ``get_user``,
    así que una sesión abierta deja de valer en cuanto el correo sale de la lista.
    """

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and esta_permitido(getattr(user, "email", ""))
