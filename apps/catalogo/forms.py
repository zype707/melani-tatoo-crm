from django import forms

from apps.nucleo.imagenes import procesar_imagen

from .models import DisenoFlash


class DisenoForm(forms.ModelForm):
    archivo = forms.FileField(
        label="Imagen",
        required=False,
        help_text="JPG, PNG o WebP. Se guarda sin datos de ubicación.",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )

    class Meta:
        model = DisenoFlash
        fields = [
            "titulo",
            "precio",
            "tamano",
            "zona_sugerida",
            "descripcion",
            "estado",
            "repetible",
            "publico",
            "orden",
        ]
        widgets = {"precio": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "decimal"})}

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if not archivo:
            if not self.instance.pk:
                raise forms.ValidationError("Sube la imagen del diseño.")
            return None
        return procesar_imagen(archivo, max_lado=2000, lado_miniatura=600)

    def save(self, commit=True):
        diseno = super().save(commit=False)
        procesada = self.cleaned_data.get("archivo")
        if procesada:
            from apps.nucleo.archivos import borrar_archivo

            if diseno.pk:
                borrar_archivo(diseno.imagen)
                borrar_archivo(diseno.miniatura)
            diseno.imagen, diseno.miniatura = procesada
        if commit:
            diseno.save()
        return diseno
