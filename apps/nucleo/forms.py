from django import forms

from .imagenes import procesar_logo
from .models import AjustesEstudio

SECCIONES = {
    "marca": (
        "Marca y contacto",
        ["nombre", "nombre_artista", "eslogan", "telefono", "email", "direccion", "instagram", "web"],
    ),
    "reservas": (
        "Reservas y textos",
        [
            "reservas_activas",
            "edad_minima",
            "reserva_bienvenida",
            "politica_senas",
            "texto_cuidados",
            "texto_privacidad",
        ],
    ),
    "legal": ("Consentimiento", ["texto_consentimiento", "retencion_consentimientos_anios"]),
    "retencion": (
        "Fidelización",
        ["recordatorio_dias_antes", "meses_inactividad", "reactivaciones_por_dia", "campana_por_dia", "umbral_vip"],
    ),
    "ia": ("Asistente IA", ["ia_activa", "ia_tono", "ia_ejemplos", "ia_limite_mensual"]),
}


def formulario_ajustes(seccion: str):
    campos = SECCIONES[seccion][1]

    class AjustesForm(forms.ModelForm):
        class Meta:
            model = AjustesEstudio
            fields = campos
            widgets = {
                "reserva_bienvenida": forms.Textarea(attrs={"rows": 3}),
                "politica_senas": forms.Textarea(attrs={"rows": 3}),
                "texto_cuidados": forms.Textarea(attrs={"rows": 4}),
                "texto_privacidad": forms.Textarea(attrs={"rows": 4}),
                "texto_consentimiento": forms.Textarea(attrs={"rows": 16}),
                "ia_tono": forms.Textarea(attrs={"rows": 3}),
                "ia_ejemplos": forms.Textarea(attrs={"rows": 8}),
            }

        def clean_edad_minima(self):
            edad = self.cleaned_data["edad_minima"]
            if edad < 16:
                raise forms.ValidationError("En Florida no se puede tatuar a menores de 16 años en ningún caso.")
            return edad

        def save(self, commit=True):
            ajustes = super().save(commit=False)
            if "texto_consentimiento" in self.changed_data:
                ajustes.version_consentimiento += 1
            if commit:
                ajustes.save()
            return ajustes

    return AjustesForm


class LogoForm(forms.Form):
    logo = forms.FileField(
        label="Logotipo",
        required=False,
        help_text="PNG cuadrado, idealmente con fondo transparente.",
        widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
    )
    quitar = forms.BooleanField(label="Quitar el logotipo", required=False)

    def clean_logo(self):
        archivo = self.cleaned_data.get("logo")
        return procesar_logo(archivo) if archivo else None


class ConfirmarCodigoForm(forms.Form):
    codigo = forms.CharField(
        label="Código de tu app autenticadora",
        max_length=8,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "class": "entrada-codigo"}
        ),
    )
