from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.clientes.models import Cliente, Tatuaje
from apps.clientes.servicios import normalizar_telefono
from apps.finanzas.models import Metodo, Pago
from apps.nucleo.formularios import CampoImagenes, EntradaFecha, EntradaHora, procesar_lista_imagenes

from . import servicios
from .models import Bloqueo, Cita, EntradaListaEspera, EstadoCita, HorarioLaboral, SolicitudReserva, TipoCita


class CitaForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.activos(), required=False, widget=forms.HiddenInput)
    nuevo_cliente_nombre = forms.CharField(label=_("Nombre"), max_length=80, required=False)
    nuevo_cliente_telefono = forms.CharField(
        label=_("Teléfono"), max_length=30, required=False, widget=forms.TextInput(attrs={"type": "tel"})
    )
    fecha = forms.DateField(label=_("Día"), widget=EntradaFecha())
    hora = forms.TimeField(label=_("Hora"), widget=EntradaHora(attrs={"step": 900}))
    duracion = forms.IntegerField(
        label=_("Duración (min)"),
        min_value=15,
        max_value=12 * 60,
        widget=forms.NumberInput(attrs={"step": 15, "inputmode": "numeric"}),
    )
    nuevo_tatuaje = forms.CharField(
        label=_("…o crea un tatuaje nuevo"), max_length=120, required=False, help_text=_("Título del proyecto")
    )
    fuera_de_horario = forms.BooleanField(label=_("Sé que es fuera de mi horario"), required=False)

    class Meta:
        model = Cita
        fields = ["cliente", "tipo", "estado", "tatuaje", "descripcion", "precio", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 3}),
            "precio": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoCita.objects.filter(activo=True)
        self.fields["tipo"].empty_label = None
        self.fields["estado"].choices = (
            [(k, v) for k, v in EstadoCita.choices if k in (EstadoCita.CONFIRMADA, EstadoCita.SOLICITADA)]
            if not self.instance.pk
            else EstadoCita.choices
        )
        cliente_id = self.data.get("cliente") or self.initial.get("cliente") or self.instance.cliente_id
        if hasattr(cliente_id, "pk"):
            cliente_id = cliente_id.pk
        self.fields["tatuaje"].queryset = (
            Tatuaje.objects.filter(cliente_id=cliente_id) if str(cliente_id or "").isdigit() else Tatuaje.objects.none()
        )
        self.fields["tatuaje"].required = False
        self.fields["tatuaje"].empty_label = _("— Sin tatuaje asociado —")
        if self.instance.pk:
            local = timezone.localtime(self.instance.inicio)
            self.initial.setdefault("fecha", local.date())
            self.initial.setdefault("hora", local.time().replace(second=0, microsecond=0))
            self.initial.setdefault("duracion", self.instance.duracion_minutos)
        self.fields["cliente"].widget.attrs.update(
            {
                "hx-get": reverse("clientes:tatuajes_de_cliente"),
                "hx-trigger": "change",
                "hx-target": "#id_tatuaje",
                "hx-swap": "innerHTML",
            }
        )
        # Las duraciones por tipo viajan en el HTML para autocompletar (sin JS en línea)
        self.duraciones = {t.pk: t.duracion_minutos for t in self.fields["tipo"].queryset}

    def clean(self):
        datos = super().clean()
        cliente = datos.get("cliente")
        if not cliente:
            nombre = (datos.get("nuevo_cliente_nombre") or "").strip()
            if not nombre:
                raise forms.ValidationError(_("Elige un cliente o escribe el nombre de uno nuevo."))
            try:
                datos["nuevo_cliente_telefono"] = normalizar_telefono(datos.get("nuevo_cliente_telefono", ""))
            except forms.ValidationError as exc:
                self.add_error("nuevo_cliente_telefono", exc)
        if not all(datos.get(k) for k in ("fecha", "hora", "duracion")):
            return datos
        inicio = timezone.make_aware(datetime.combine(datos["fecha"], datos["hora"]))
        fin = inicio + timedelta(minutes=datos["duracion"])
        datos["inicio"], datos["fin"] = inicio, fin
        estado = datos.get("estado") or EstadoCita.CONFIRMADA
        if estado in (EstadoCita.SOLICITADA, EstadoCita.CONFIRMADA, EstadoCita.REALIZADA):
            for motivo in servicios.conflictos(inicio, fin, self.instance.pk):
                self.add_error(None, motivo)
            if servicios.fuera_de_horario(inicio, fin) and not datos.get("fuera_de_horario"):
                self.add_error(
                    "fuera_de_horario",
                    _("Está fuera de tu horario laboral. Marca la casilla si quieres guardarla igual."),
                )
        tatuaje = datos.get("tatuaje")
        if tatuaje and cliente and tatuaje.cliente_id != cliente.pk:
            self.add_error("tatuaje", _("Ese tatuaje es de otro cliente."))
        return datos

    def save(self, commit=True):
        cita = super().save(commit=False)
        datos = self.cleaned_data
        if not datos.get("cliente"):
            cita.cliente = Cliente.objects.create(
                nombre=datos["nuevo_cliente_nombre"].strip(), telefono=datos.get("nuevo_cliente_telefono", "")
            )
        cita.inicio, cita.fin = datos["inicio"], datos["fin"]
        if datos.get("nuevo_tatuaje"):
            cita.tatuaje = Tatuaje.objects.create(cliente=cita.cliente, titulo=datos["nuevo_tatuaje"].strip())
        if commit:
            cita.save()
        return cita


class CancelarForm(forms.Form):
    motivo = forms.CharField(label=_("Motivo"), max_length=200, required=False)
    cancelada_por = forms.ChoiceField(
        label=_("¿Quién cancela?"),
        choices=Cita.CanceladaPor.choices,
        initial=Cita.CanceladaPor.CLIENTE,
        widget=forms.RadioSelect,
    )


class CerrarSesionForm(forms.Form):
    importe = forms.DecimalField(
        label=_("Cobrado hoy"),
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "decimal"}),
        help_text=_("Sin contar la seña ya registrada."),
    )
    metodo = forms.ChoiceField(label=_("Método"), choices=Metodo.choices)
    notas_sesion = forms.CharField(
        label=_("Notas de la sesión"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Tintas, agujas, cómo reaccionó la piel, qué falta…"),
    )
    terminado = forms.BooleanField(label=_("El tatuaje queda terminado"), required=False)


class PagoForm(forms.ModelForm):
    class Meta:
        model = Pago
        fields = ["tipo", "importe", "metodo", "fecha", "notas"]
        widgets = {
            "fecha": EntradaFecha(),
            "importe": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "decimal"}),
        }


class TipoCitaForm(forms.ModelForm):
    class Meta:
        model = TipoCita
        fields = ["nombre", "categoria", "duracion_minutos", "color", "deposito_sugerido", "activo", "orden"]
        widgets = {"color": forms.RadioSelect}


class BloqueoForm(forms.ModelForm):
    desde_fecha = forms.DateField(label=_("Desde el día"), widget=EntradaFecha())
    desde_hora = forms.TimeField(label=_("Hora"), required=False, widget=EntradaHora())
    hasta_fecha = forms.DateField(label=_("Hasta el día"), widget=EntradaFecha())
    hasta_hora = forms.TimeField(label=_("Hora"), required=False, widget=EntradaHora())

    class Meta:
        model = Bloqueo
        fields = ["tipo", "motivo"]

    def clean(self):
        datos = super().clean()
        if not datos.get("desde_fecha") or not datos.get("hasta_fecha"):
            return datos
        desde_h = datos.get("desde_hora") or datetime.min.time()
        inicio = timezone.make_aware(datetime.combine(datos["desde_fecha"], desde_h))
        if datos.get("hasta_hora"):
            fin = timezone.make_aware(datetime.combine(datos["hasta_fecha"], datos["hasta_hora"]))
        else:
            fin = timezone.make_aware(datetime.combine(datos["hasta_fecha"] + timedelta(days=1), datetime.min.time()))
        if fin <= inicio:
            raise forms.ValidationError(_("El final debe ser posterior al inicio."))
        datos["inicio"], datos["fin"] = inicio, fin
        ocupadas = Cita.objects.solapadas(inicio, fin).count()
        if ocupadas and not self.data.get("confirmar"):
            self.add_error(
                None,
                _("Hay %(ocupadas)s cita(s) en ese periodo. Reprográmalas o pulsa «Bloquear igualmente».")
                % {"ocupadas": ocupadas},
            )
            self.necesita_confirmar = True
        return datos

    def save(self, commit=True):
        bloqueo = super().save(commit=False)
        bloqueo.inicio, bloqueo.fin = self.cleaned_data["inicio"], self.cleaned_data["fin"]
        if commit:
            bloqueo.save()
        return bloqueo


class HorarioForm(forms.Form):
    """Dos tramos posibles por día (mañana y tarde)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existentes = {}
        for h in HorarioLaboral.objects.all():
            existentes.setdefault(h.dia_semana, []).append(h)
        self.dias = []
        for dia, nombre in HorarioLaboral.Dia.choices:
            filas = []
            for n in (1, 2):
                ini, fin = f"d{dia}_{n}_ini", f"d{dia}_{n}_fin"
                self.fields[ini] = forms.TimeField(
                    label=_("%(nombre)s tramo %(n)s desde") % {"nombre": nombre, "n": n},
                    required=False,
                    widget=EntradaHora(),
                )
                self.fields[fin] = forms.TimeField(
                    label=_("%(nombre)s tramo %(n)s hasta") % {"nombre": nombre, "n": n},
                    required=False,
                    widget=EntradaHora(),
                )
                actual = existentes.get(dia, [])
                if len(actual) >= n:
                    self.initial[ini] = actual[n - 1].hora_inicio
                    self.initial[fin] = actual[n - 1].hora_fin
                filas.append((self[ini], self[fin]))
            self.dias.append((nombre, filas))

    def clean(self):
        datos = super().clean()
        self.tramos = []
        for dia, nombre in HorarioLaboral.Dia.choices:
            for n in (1, 2):
                ini, fin = datos.get(f"d{dia}_{n}_ini"), datos.get(f"d{dia}_{n}_fin")
                if ini and fin:
                    if fin <= ini:
                        self.add_error(
                            f"d{dia}_{n}_fin", _("%(nombre)s: la hora final debe ser posterior.") % {"nombre": nombre}
                        )
                    else:
                        self.tramos.append(HorarioLaboral(dia_semana=dia, hora_inicio=ini, hora_fin=fin))
                elif ini or fin:
                    self.add_error(
                        f"d{dia}_{n}_ini",
                        _("%(nombre)s: completa las dos horas del tramo %(n)s.") % {"nombre": nombre, "n": n},
                    )
        return datos

    def save(self):
        HorarioLaboral.objects.all().delete()
        HorarioLaboral.objects.bulk_create(self.tramos)


class ListaEsperaForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.activos(), widget=forms.HiddenInput)
    dias = forms.TypedMultipleChoiceField(
        label=_("Días que le van bien"),
        choices=HorarioLaboral.Dia.choices,
        coerce=int,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Sin marcar = cualquier día."),
    )

    class Meta:
        model = EntradaListaEspera
        fields = ["cliente", "tipo", "dias", "franja", "notas", "prioritaria"]
        widgets = {"franja": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoCita.objects.filter(activo=True)
        self.fields["tipo"].required = False


class ReprogramarClienteForm(forms.Form):
    texto = forms.CharField(
        label=_("¿Qué días u horas te vendrían mejor?"),
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Ej.: cualquier tarde de la semana que viene")}),
    )


class CancelarClienteForm(forms.Form):
    motivo = forms.CharField(label=_("Motivo (opcional)"), max_length=200, required=False)


# --- Página pública de reservas --------------------------------------------------------------

FIRMA_TIEMPO = "reserva-tiempo"


class SolicitudForm(forms.ModelForm):
    """Formulario público. Anti-spam: campo trampa invisible y tiempo mínimo de relleno."""

    imagenes = CampoImagenes(
        label=_("Imágenes de referencia"),
        required=False,
        help_text=_("Hasta 5 imágenes (JPG, PNG o WebP). Se eliminan los datos de ubicación."),
    )
    acepta_privacidad = forms.BooleanField(label=_("He leído y acepto el aviso de privacidad"))
    acepta_marketing = forms.BooleanField(
        label=_("Quiero recibir felicitaciones, flash disponibles y huecos libres"), required=False
    )
    web = forms.CharField(
        required=False,
        label=_("No rellenes este campo"),
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )
    t = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = SolicitudReserva
        fields = [
            "nombre",
            "apellidos",
            "telefono",
            "email",
            "instagram",
            "fecha_nacimiento",
            "descripcion",
            "zona",
            "tamano",
            "estilo",
            "medidas",
            "fechas_preferidas",
            "presupuesto",
            "primer_tatuaje",
            "acepta_marketing",
        ]
        widgets = {
            "fecha_nacimiento": EntradaFecha(),
            "telefono": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "nombre": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "apellidos": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "descripcion": forms.Textarea(
                attrs={
                    "rows": 6,
                    "maxlength": 3000,
                    "placeholder": _("Qué quieres tatuarte, cómo lo imaginas, colores, significado…"),
                }
            ),
            "fechas_preferidas": forms.TextInput(
                attrs={"placeholder": _("Ej.: tardes entre semana, a partir de enero")}
            ),
            "instagram": forms.TextInput(attrs={"placeholder": "tu_usuario"}),
        }

    def __init__(self, *args, edad_minima: int = 18, **kwargs):
        super().__init__(*args, **kwargs)
        self.edad_minima = edad_minima
        self.fields["email"].required = False
        self.fields["descripcion"].label = _("Cuéntame tu idea")
        if not self.is_bound:
            self.initial["t"] = signing.TimestampSigner(salt=FIRMA_TIEMPO).sign(str(timezone.now().timestamp()))

    def clean_t(self):
        try:
            signing.TimestampSigner(salt=FIRMA_TIEMPO).unsign(self.cleaned_data["t"], max_age=60 * 60 * 3)
            enviado = float(signing.TimestampSigner(salt=FIRMA_TIEMPO).unsign(self.cleaned_data["t"]))
        except (signing.BadSignature, ValueError) as exc:
            raise forms.ValidationError(_("El formulario caducó. Recarga la página.")) from exc
        if timezone.now().timestamp() - enviado < 3:
            raise forms.ValidationError(_("Has ido demasiado rápido. Inténtalo otra vez."))
        return self.cleaned_data["t"]

    def clean_web(self):
        if self.cleaned_data.get("web"):
            raise forms.ValidationError(_("Solicitud no válida."))
        return ""

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])

    def clean_instagram(self):
        return (self.cleaned_data.get("instagram") or "").strip().lstrip("@")

    def clean_fecha_nacimiento(self):
        n = self.cleaned_data["fecha_nacimiento"]
        hoy = timezone.localdate()
        edad = hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))
        if edad > 110 or n > hoy:
            raise forms.ValidationError(_("Revisa la fecha de nacimiento."))
        if edad < self.edad_minima:
            raise forms.ValidationError(
                _("Para tatuarte en el estudio necesitas tener al menos %(edad_minima)s años.")
                % {"edad_minima": self.edad_minima}
            )
        return n

    def clean_imagenes(self):
        return procesar_lista_imagenes(self.cleaned_data.get("imagenes") or [], settings.SUBIDAS_MAX_IMAGENES)


class RechazoForm(forms.Form):
    motivo = forms.CharField(label=_("Motivo (solo para ti)"), max_length=200, required=False)
