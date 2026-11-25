from django import forms
from django.utils.translation import gettext_lazy as _


class FormularioAcceso(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    password = forms.CharField(
        label=_("Contraseña"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class FormularioCodigo(forms.Form):
    codigo = forms.CharField(
        label=_("Código de 6 dígitos"),
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": r"[0-9 ]*",
                "autofocus": True,
                "class": "entrada-codigo",
            }
        ),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].replace(" ", "")
        if not codigo.isdigit() or len(codigo) != 6:
            raise forms.ValidationError(_("Escribe los 6 dígitos que muestra tu app."))
        return codigo


class FormularioRecuperacion(forms.Form):
    codigo = forms.CharField(
        label=_("Código de recuperación"),
        max_length=20,
        help_text=_("Formato xxxxx-xxxxx. Cada código solo sirve una vez."),
        widget=forms.TextInput(attrs={"autocomplete": "off", "autofocus": True, "spellcheck": "false"}),
    )


class FormularioPerfil(forms.Form):
    nombre = forms.CharField(label=_("Tu nombre"), max_length=120)


class FormularioAlta(forms.Form):
    """Primer acceso. Solo funciona para correos de CORREOS_PERMITIDOS y con el código de alta."""

    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        help_text=_("Debe ser uno de los correos autorizados del estudio."),
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    nombre = forms.CharField(
        label=_("Tu nombre"), max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    codigo_alta = forms.CharField(
        label=_("Código de alta"),
        strip=True,
        help_text=_("Te lo da quien administra el despliegue (variable CODIGO_ALTA)."),
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
    )
    password1 = forms.CharField(
        label=_("Contraseña"),
        strip=False,
        help_text=_("Mínimo 12 caracteres."),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label=_("Repite la contraseña"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get("password1") and datos.get("password2") and datos["password1"] != datos["password2"]:
            self.add_error("password2", _("Las contraseñas no coinciden."))
        return datos
