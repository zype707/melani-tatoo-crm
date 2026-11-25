"""Lista blanca de correos que pueden entrar (variable de entorno CORREOS_PERMITIDOS).

- Solo los correos de la lista pueden iniciar sesión o darse de alta.
- Quitar un correo de la lista corta su acceso en la siguiente petición
  (el backend deja de devolver a esa usuaria, aunque tenga sesión abierta).
- El primer correo de la lista es la propietaria; el resto, ayudantes.
- El alta en el primer acceso exige además el código de CODIGO_ALTA.

Se lee siempre de ``settings`` en el momento de usarlo (los tests lo cambian).
"""

import hmac

from django.conf import settings


def normalizar(email: str | None) -> str:
    return (email or "").strip().lower()


def correos_permitidos() -> list[str]:
    return [normalizar(c) for c in getattr(settings, "CORREOS_PERMITIDOS", []) if normalizar(c)]


def esta_permitido(email: str | None) -> bool:
    email = normalizar(email)
    return bool(email) and email in correos_permitidos()


def rol_para(email: str) -> str:
    """El primer correo de la lista es la propietaria; los demás, ayudantes."""
    from .models import Usuario

    lista = correos_permitidos()
    if lista and normalizar(email) == lista[0]:
        return Usuario.Rol.PROPIETARIA
    return Usuario.Rol.AYUDANTE


def alta_habilitada() -> bool:
    return bool(getattr(settings, "CODIGO_ALTA", ""))


def codigo_alta_valido(codigo: str | None) -> bool:
    esperado = getattr(settings, "CODIGO_ALTA", "") or ""
    if not esperado or not codigo:
        return False
    return hmac.compare_digest(codigo.strip().encode(), esperado.encode())
