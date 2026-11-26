from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.nucleo.auditoria import Accion, registrar
from apps.nucleo.decoradores import vista_publica
from apps.nucleo.red import ip_cliente

from . import servicios
from .forms import FormularioAcceso, FormularioPerfil
from .models import Usuario, normalizar_usuario


def _siguiente_seguro(request, url: str) -> str:
    if url and url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure()):
        return url
    return reverse("panel:inicio")


def _mensaje_bloqueo(segundos: int) -> str:
    minutos = max(1, round(segundos / 60))
    return _("Demasiados intentos. Por seguridad, espera %(minutos)s min antes de volver a probar.") % {
        "minutos": minutos
    }


# --- Acceso --------------------------------------------------------------------------


@vista_publica
@never_cache
@sensitive_post_parameters("password")
def acceso(request):
    """Usuario y contraseña. La sesión dura SESION_HORAS y se renueva con cada visita."""
    if request.user.is_authenticated:
        return redirect("panel:inicio")
    form = FormularioAcceso(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nombre_usuario = normalizar_usuario(form.cleaned_data["usuario"])
        ip = ip_cliente(request)
        espera = servicios.segundos_bloqueo(nombre_usuario, ip)
        if espera:
            registrar(request, Accion.LOGIN_BLOQUEADO, f"Bloqueado: {nombre_usuario}")
            form.add_error(None, _mensaje_bloqueo(espera))
        else:
            usuario = authenticate(request, username=nombre_usuario, password=form.cleaned_data["password"])
            if usuario is None:
                servicios.registrar_intento(nombre_usuario, ip, False)
                existe = Usuario.objects.filter(usuario__iexact=nombre_usuario).exists()
                motivo = "Contraseña incorrecta" if existe else "Usuario inexistente"
                registrar(request, Accion.LOGIN_FALLO, f"{motivo}: {nombre_usuario}")
                form.add_error(None, _("Usuario o contraseña incorrectos."))
            else:
                servicios.registrar_intento(nombre_usuario, ip, True)
                login(request, usuario)
                registrar(request, Accion.LOGIN_OK, "Inicio de sesión")
                return redirect(_siguiente_seguro(request, request.GET.get("next", "")))
    return render(request, "cuentas/acceso.html", {"form": form})


@require_POST
def salir(request):
    registrar(request, Accion.LOGOUT)
    logout(request)
    messages.info(request, _("Has cerrado sesión."))
    return redirect("cuentas:login")


# --- Mi cuenta ---------------------------------------------------------------------------


@never_cache
@sensitive_post_parameters("old_password", "new_password1", "new_password2")
def cuenta(request):
    perfil = FormularioPerfil(initial={"nombre": request.user.nombre})
    password = PasswordChangeForm(request.user)

    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "perfil":
            perfil = FormularioPerfil(request.POST)
            if perfil.is_valid():
                request.user.nombre = perfil.cleaned_data["nombre"]
                request.user.save(update_fields=["nombre"])
                messages.success(request, _("Nombre actualizado."))
                return redirect("cuentas:cuenta")
        elif accion == "password":
            password = PasswordChangeForm(request.user, request.POST)
            if password.is_valid():
                usuario = password.save()
                update_session_auth_hash(request, usuario)
                registrar(request, Accion.PASSWORD_CAMBIADA)
                messages.success(request, _("Contraseña cambiada."))
                return redirect("cuentas:cuenta")

    return render(request, "cuentas/cuenta.html", {"perfil": perfil, "password": password})
