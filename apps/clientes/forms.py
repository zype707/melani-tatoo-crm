from django import forms
from django.conf import settings

from apps.nucleo.formularios import CampoImagenes, EntradaFecha, procesar_lista_imagenes

from .models import Cliente, DatosSalud, Etiqueta, FotoTatuaje, NotaCliente, OrigenConsentimiento, Tatuaje
from .servicios import normalizar_telefono

ORIGENES_ALTA = [(k, v) for k, v in OrigenConsentimiento.choices if k != OrigenConsentimiento.PETICION_BAJA]


class ClienteForm(forms.ModelForm):
    nuevas_etiquetas = forms.CharField(
        label="Nuevas etiquetas", required=False, help_text="Separadas por comas. Ej.: VIP, proyecto grande"
    )
    marketing = forms.BooleanField(label="Acepta recibir felicitaciones y promociones", required=False)
    marketing_origen = forms.ChoiceField(label="¿Cómo lo aceptó?", choices=[("", "—"), *ORIGENES_ALTA], required=False)

    class Meta:
        model = Cliente
        fields = [
            "nombre",
            "apellidos",
            "telefono",
            "email",
            "instagram",
            "fecha_nacimiento",
            "canal_preferido",
            "origen",
            "etiquetas",
            "contacto_bloqueado",
            "notas",
        ]
        widgets = {
            "fecha_nacimiento": EntradaFecha(),
            "telefono": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "instagram": forms.TextInput(attrs={"placeholder": "usuario"}),
            "canal_preferido": forms.RadioSelect,
            "etiquetas": forms.CheckboxSelectMultiple,
            "notas": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["etiquetas"].queryset = Etiqueta.objects.all()
        self.fields["etiquetas"].required = False
        if self.instance.pk:
            self.fields["marketing"].initial = self.instance.marketing_consentimiento
            self.fields["marketing_origen"].initial = self.instance.marketing_origen

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data.get("telefono", ""))

    def clean_instagram(self):
        return (self.cleaned_data.get("instagram") or "").strip().lstrip("@")

    def clean(self):
        datos = super().clean()
        cambia_a_si = datos.get("marketing") and not (self.instance.pk and self.instance.marketing_consentimiento)
        if cambia_a_si and not datos.get("marketing_origen"):
            self.add_error("marketing_origen", "Indica cómo dio su consentimiento (queda registrado).")
        if not datos.get("telefono") and not datos.get("email") and not datos.get("instagram"):
            self.add_error("telefono", "Añade al menos un dato de contacto.")
        return datos

    def save(self, usuario=None):
        estaba = bool(self.instance.pk and self.instance.marketing_consentimiento)
        cliente = super().save()
        for nombre in [n.strip() for n in self.cleaned_data.get("nuevas_etiquetas", "").split(",") if n.strip()]:
            etiqueta = Etiqueta.objects.filter(nombre__iexact=nombre[:40]).first() or Etiqueta.objects.create(
                nombre=nombre[:40]
            )
            cliente.etiquetas.add(etiqueta)
        quiere = self.cleaned_data.get("marketing")
        if quiere and not estaba:
            cliente.dar_consentimiento(self.cleaned_data["marketing_origen"], usuario)
        elif estaba and not quiere:
            cliente.retirar_consentimiento(OrigenConsentimiento.PETICION_BAJA, usuario, "Desde la ficha")
        return cliente


class ClienteRapidoForm(forms.Form):
    """Alta mínima desde el formulario de cita."""

    nombre = forms.CharField(label="Nombre", max_length=80)
    telefono = forms.CharField(label="Teléfono", max_length=30, widget=forms.TextInput(attrs={"type": "tel"}))

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])


class DatosSaludForm(forms.ModelForm):
    class Meta:
        model = DatosSalud
        fields = [
            "alergias",
            "medicacion",
            "anticoagulantes",
            "diabetes",
            "epilepsia",
            "problemas_cardiacos",
            "embarazo_lactancia",
            "condiciones_piel",
            "otras",
        ]
        widgets = {
            "alergias": forms.Textarea(attrs={"rows": 2}),
            "medicacion": forms.Textarea(attrs={"rows": 2}),
            "condiciones_piel": forms.Textarea(attrs={"rows": 2}),
            "otras": forms.Textarea(attrs={"rows": 3}),
        }


class MarketingForm(forms.Form):
    accion = forms.ChoiceField(choices=[("alta", "alta"), ("baja", "baja")])
    origen = forms.ChoiceField(choices=OrigenConsentimiento.choices)
    notas = forms.CharField(max_length=200, required=False)


class NotaForm(forms.ModelForm):
    class Meta:
        model = NotaCliente
        fields = ["texto", "origen"]
        widgets = {
            "texto": forms.Textarea(attrs={"rows": 3, "placeholder": "Escribe o dicta una nota…"}),
            "origen": forms.HiddenInput,
        }


class TatuajeForm(forms.ModelForm):
    class Meta:
        model = Tatuaje
        fields = [
            "titulo",
            "zona",
            "estilo",
            "tamano",
            "medidas",
            "estado",
            "fecha_inicio",
            "fecha_fin",
            "sesiones_previstas",
            "precio_total",
            "retoque_hecho",
            "notas",
        ]
        widgets = {
            "fecha_inicio": EntradaFecha(),
            "fecha_fin": EntradaFecha(),
            "notas": forms.Textarea(attrs={"rows": 3}),
            "precio_total": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "decimal"}),
        }

    def clean(self):
        datos = super().clean()
        if datos.get("estado") == Tatuaje.Estado.TERMINADO and not datos.get("fecha_fin"):
            datos["fecha_fin"] = datos.get("fecha_inicio")
        if datos.get("fecha_inicio") and datos.get("fecha_fin") and datos["fecha_fin"] < datos["fecha_inicio"]:
            self.add_error("fecha_fin", "No puede ser anterior a la primera sesión.")
        return datos


class FotosForm(forms.Form):
    imagenes = CampoImagenes(label="Fotos", help_text="JPG, PNG o WebP. Se eliminan los datos de ubicación.")
    tipo = forms.ChoiceField(label="Tipo", choices=FotoTatuaje.Tipo.choices, initial=FotoTatuaje.Tipo.RESULTADO)
    nota = forms.CharField(label="Nota", max_length=160, required=False)

    def clean_imagenes(self):
        return procesar_lista_imagenes(self.cleaned_data["imagenes"], settings.SUBIDAS_MAX_IMAGENES * 2)


class EtiquetaForm(forms.ModelForm):
    class Meta:
        model = Etiqueta
        fields = ["nombre"]


class ConsentimientoForm(forms.Form):
    """Lo rellena el cliente en la tablet o el móvil del estudio."""

    nombre_firmante = forms.CharField(label="Nombre y apellidos", max_length=200)
    fecha_nacimiento = forms.DateField(label="Fecha de nacimiento", widget=EntradaFecha())
    alergias = forms.CharField(
        label="¿Alergias? (látex, pigmentos, medicamentos…)", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    medicacion = forms.CharField(
        label="¿Tomas alguna medicación?", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    anticoagulantes = forms.BooleanField(label="Tomo anticoagulantes o tengo problemas de coagulación", required=False)
    diabetes = forms.BooleanField(label="Tengo diabetes", required=False)
    epilepsia = forms.BooleanField(label="Tengo epilepsia", required=False)
    problemas_cardiacos = forms.BooleanField(label="Tengo problemas cardíacos", required=False)
    embarazo_lactancia = forms.BooleanField(label="Estoy embarazada o en lactancia", required=False)
    condiciones_piel = forms.CharField(
        label="¿Alguna condición de la piel? (psoriasis, queloides…)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    otras = forms.CharField(label="¿Algo más que deba saber?", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    acepto = forms.BooleanField(label="He leído el texto y doy mi consentimiento")
    veraz = forms.BooleanField(label="Declaro que la información de salud es verdadera y completa")
    autoriza_fotos = forms.BooleanField(
        label="Autorizo fotos de mi tatuaje para el portfolio del estudio", required=False
    )
    acepta_marketing = forms.BooleanField(label="Quiero recibir felicitaciones y novedades por mensaje", required=False)
    firma = forms.CharField(widget=forms.HiddenInput, error_messages={"required": "Falta tu firma."})

    CAMPOS_SALUD = [
        "alergias",
        "medicacion",
        "anticoagulantes",
        "diabetes",
        "epilepsia",
        "problemas_cardiacos",
        "embarazo_lactancia",
        "condiciones_piel",
        "otras",
    ]

    def __init__(self, *args, edad_minima: int = 18, **kwargs):
        super().__init__(*args, **kwargs)
        self.edad_minima = edad_minima

    def clean_fecha_nacimiento(self):
        from django.utils import timezone

        n = self.cleaned_data["fecha_nacimiento"]
        hoy = timezone.localdate()
        edad = hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))
        if edad < self.edad_minima:
            raise forms.ValidationError(f"Hace falta tener al menos {self.edad_minima} años.")
        return n

    def clean_firma(self):
        from .consentimiento import decodificar_firma

        decodificar_firma(self.cleaned_data["firma"])  # valida (vacía, tamaño, formato)
        return self.cleaned_data["firma"]

    def salud(self) -> dict:
        return {c: self.cleaned_data.get(c) for c in self.CAMPOS_SALUD}
