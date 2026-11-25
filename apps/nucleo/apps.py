from django.apps import AppConfig


class NucleoConfig(AppConfig):
    name = "apps.nucleo"
    label = "nucleo"
    verbose_name = "Núcleo"

    def ready(self):
        # Django 6.1 permite cambiar la etiqueta de la opción vacía de los <select>.
        from django.db.models import fields

        fields.BLANK_CHOICE_LABEL = "— Elige —"
