from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def revisar_acceso(app_configs, **kwargs):
    avisos = []
    if not getattr(settings, "CORREOS_PERMITIDOS", []):
        avisos.append(
            Warning(
                "CORREOS_PERMITIDOS está vacía: nadie podrá iniciar sesión.",
                hint="Define CORREOS_PERMITIDOS=tu@correo.com,otra@correo.com (el primero es la propietaria).",
                id="cuentas.W001",
            )
        )
    codigo = getattr(settings, "CODIGO_ALTA", "")
    if codigo and len(codigo) < 16:
        avisos.append(
            Error(
                "CODIGO_ALTA es demasiado corto (mínimo 16 caracteres).",
                hint="Usa una cadena larga y aleatoria, o déjala vacía para desactivar el alta.",
                id="cuentas.E001",
            )
        )
    return avisos
