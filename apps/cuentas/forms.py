from django import forms


class FormularioAcceso(forms.Form):
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class FormularioCodigo(forms.Form):
    codigo = forms.CharField(
        label="Código de 6 dígitos",
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
            raise forms.ValidationError("Escribe los 6 dígitos que muestra tu app.")
        return codigo


class FormularioRecuperacion(forms.Form):
    codigo = forms.CharField(
        label="Código de recuperación",
        max_length=20,
        help_text="Formato xxxxx-xxxxx. Cada código solo sirve una vez.",
        widget=forms.TextInput(attrs={"autocomplete": "off", "autofocus": True, "spellcheck": "false"}),
    )


class FormularioPerfil(forms.Form):
    nombre = forms.CharField(label="Tu nombre", max_length=120)
