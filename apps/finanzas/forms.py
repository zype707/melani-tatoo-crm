from django import forms
from django.utils.translation import gettext_lazy as _

from apps.clientes.models import Cliente
from apps.nucleo.formularios import EntradaFecha

from .models import Gasto, Pago


class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ["fecha", "categoria", "concepto", "importe", "metodo", "notas"]
        widgets = {
            "fecha": EntradaFecha(),
            "importe": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
        }


class PagoSueltoForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.activos(), required=False, widget=forms.HiddenInput)

    class Meta:
        model = Pago
        fields = ["cliente", "tipo", "importe", "metodo", "fecha", "notas"]
        widgets = {
            "fecha": EntradaFecha(),
            "importe": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
        }


class ExportarForm(forms.Form):
    desde = forms.DateField(label=_("Desde"), widget=EntradaFecha(attrs={"class": "select-compacto"}))
    hasta = forms.DateField(label=_("Hasta"), widget=EntradaFecha(attrs={"class": "select-compacto"}))

    def clean(self):
        datos = super().clean()
        if datos.get("desde") and datos.get("hasta") and datos["hasta"] < datos["desde"]:
            raise forms.ValidationError(_("La fecha final es anterior a la inicial."))
        return datos
