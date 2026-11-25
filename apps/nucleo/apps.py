from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class NucleoConfig(AppConfig):
    name = "apps.nucleo"
    label = "nucleo"
    verbose_name = gettext_lazy("Núcleo")

    def ready(self):
        # Django 6.1 permite cambiar la etiqueta de la opción vacía de los <select>.
        from django.db.models import fields

        fields.BLANK_CHOICE_LABEL = gettext_lazy("— Elige —")
