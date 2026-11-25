from django.apps import AppConfig


class CuentasConfig(AppConfig):
    name = "apps.cuentas"
    label = "cuentas"
    verbose_name = "Cuentas"

    def ready(self):
        from . import checks  # noqa: F401  (registra los checks de acceso)
