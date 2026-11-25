from django import forms

from apps.clientes.models import Cliente
from apps.nucleo.formularios import EntradaFecha

from . import segmentos, variables
from .models import Campana, Categoria, FechaDestacada, PasoCuidado, Plantilla


class PlantillaForm(forms.ModelForm):
    class Meta:
        model = Plantilla
        fields = ["nombre", "categoria", "cuerpo", "es_promocional", "predeterminada", "activa"]
        widgets = {"cuerpo": forms.Textarea(attrs={"rows": 7, "data-editor-plantilla": True})}

    def clean_cuerpo(self):
        cuerpo = self.cleaned_data["cuerpo"]
        malas = variables.desconocidas(cuerpo)
        if malas:
            raise forms.ValidationError(
                "Variables que no existen: " + ", ".join("{" + v + "}" for v in malas) + ". Usa las de la lista."
            )
        return cuerpo

    def clean(self):
        datos = super().clean()
        if datos.get("categoria") in (Categoria.CUMPLEANOS, Categoria.FECHA_DESTACADA, Categoria.CAMPANA):
            datos["es_promocional"] = True  # siempre requieren consentimiento
        return datos

    def save(self, commit=True):
        plantilla = super().save(commit)
        if commit and plantilla.predeterminada:
            Plantilla.objects.filter(categoria=plantilla.categoria).exclude(pk=plantilla.pk).update(
                predeterminada=False
            )
        return plantilla


class PasoCuidadoForm(forms.ModelForm):
    class Meta:
        model = PasoCuidado
        fields = ["nombre", "dias_despues", "plantilla", "es_oferta_retoque", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].queryset = Plantilla.objects.filter(
            categoria__in=[Categoria.CUIDADO, Categoria.RETOQUE], activa=True
        )


class FechaDestacadaForm(forms.ModelForm):
    segmento = forms.ChoiceField(label="Para", choices=segmentos.OPCIONES)
    mes = forms.TypedChoiceField(
        label="Mes",
        coerce=int,
        required=False,
        empty_value=None,
        choices=[("", "—")]
        + [
            (i, m)
            for i, m in enumerate(
                [
                    "enero",
                    "febrero",
                    "marzo",
                    "abril",
                    "mayo",
                    "junio",
                    "julio",
                    "agosto",
                    "septiembre",
                    "octubre",
                    "noviembre",
                    "diciembre",
                ],
                start=1,
            )
        ],
    )

    class Meta:
        model = FechaDestacada
        fields = [
            "nombre",
            "regla",
            "mes",
            "dia",
            "semana",
            "dia_semana",
            "fecha",
            "plantilla",
            "dias_ventana",
            "segmento",
            "generar_campana",
            "activa",
        ]
        widgets = {"fecha": EntradaFecha()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].queryset = Plantilla.objects.filter(es_promocional=True, activa=True)

    def clean(self):
        datos = super().clean()
        regla = datos.get("regla")
        faltan = {
            FechaDestacada.Regla.FIJA: ["mes", "dia"],
            FechaDestacada.Regla.NTH: ["mes", "semana", "dia_semana"],
            FechaDestacada.Regla.ULTIMO: ["mes", "dia_semana"],
            FechaDestacada.Regla.UNICA: ["fecha"],
        }.get(regla, [])
        for campo in faltan:
            if datos.get(campo) in (None, ""):
                self.add_error(campo, "Necesario para esta regla.")
        if datos.get("generar_campana") and not datos.get("plantilla"):
            self.add_error("plantilla", "Elige una plantilla o desmarca «Preparar mensajes».")
        return datos


class CampanaForm(forms.ModelForm):
    segmento = forms.ChoiceField(label="Segmento", choices=segmentos.OPCIONES)

    class Meta:
        model = Campana
        fields = ["nombre", "segmento", "plantilla", "fecha_inicio", "por_dia"]
        widgets = {"fecha_inicio": EntradaFecha()}
        help_texts = {"por_dia": "Así no parece un envío masivo y puedes responder a cada persona."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].queryset = Plantilla.objects.filter(es_promocional=True, activa=True)
        self.fields["por_dia"].widget.attrs.update(min=1, max=50)

    def clean_por_dia(self):
        n = self.cleaned_data["por_dia"]
        if not 1 <= n <= 50:
            raise forms.ValidationError("Entre 1 y 50 al día.")
        return n


class MensajeLibreForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.activos(), widget=forms.HiddenInput)
    plantilla = forms.ModelChoiceField(
        label="Partir de una plantilla",
        queryset=Plantilla.objects.filter(activa=True),
        required=False,
    )
    texto = forms.CharField(label="Mensaje", widget=forms.Textarea(attrs={"rows": 6}), max_length=4000)
