from django import forms
from django.forms.renderers import TemplatesSetting
from django.utils.translation import gettext as _


class Renderizador(TemplatesSetting):
    form_template_name = "componentes/formulario.html"
    field_template_name = "componentes/campo.html"


class EntradaFecha(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class EntradaHora(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%H:%M")


class EntradaFechaHora(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%dT%H:%M")


class EntradaArchivosMultiples(forms.FileInput):
    allow_multiple_selected = True


class CampoImagenes(forms.FileField):
    """Varias imágenes en un mismo campo. Devuelve una lista de archivos."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            EntradaArchivosMultiples(attrs={"accept": "image/jpeg,image/png,image/webp", "multiple": True}),
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        limpiar = super().clean
        if isinstance(data, list | tuple):
            return [limpiar(d, initial) for d in data if d]
        return [limpiar(data, initial)] if data else []


def procesar_lista_imagenes(archivos, maximo: int) -> list:
    """Valida y re-codifica una lista de imágenes. Devuelve [(principal, miniatura), ...]."""
    from .imagenes import procesar_imagen

    if len(archivos) > maximo:
        raise forms.ValidationError(_("Como máximo %(maximo)s imágenes por envío.") % {"maximo": maximo})
    return [procesar_imagen(a) for a in archivos]
