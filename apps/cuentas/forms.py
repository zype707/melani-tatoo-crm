from django import forms
from django.utils.translation import gettext_lazy as _

# Atributos para que el gestor de contraseñas del navegador reconozca el formulario,
# ofrezca guardar las credenciales y las rellene solo la próxima vez.
ATRIBUTOS_USUARIO = {
    "autocomplete": "username",
    "autocapitalize": "none",
    "autocorrect": "off",
    "spellcheck": "false",
}


class FormularioAcceso(forms.Form):
    usuario = forms.CharField(
        label=_("Usuario"),
        max_length=150,
        widget=forms.TextInput(attrs={**ATRIBUTOS_USUARIO, "autofocus": True}),
    )
    password = forms.CharField(
        label=_("Contraseña"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class FormularioPerfil(forms.Form):
    nombre = forms.CharField(label=_("Tu nombre"), max_length=120)
