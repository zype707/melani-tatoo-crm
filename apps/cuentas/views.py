import time

from django.contrib import messages
from django.contrib.auth import authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django_otp import login as otp_login

from apps.nucleo.auditoria import Accion, registrar
from apps.nucleo.decoradores import vista_publica
from apps.nucleo.red import ip_cliente

from . import permitidos, servicios
from .forms import FormularioAcceso, FormularioAlta, FormularioCodigo, FormularioPerfil, FormularioRecuperacion
from .models import DispositivoRecuperacion, IntentoAcceso, Usuario

CLAVE_DISPOSITIVO_NUEVO = "_totp_nuevo"
CLAVE_RECONFIGURAR = "_reconfigurar_ok"


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
    if request.user.is_authenticated and request.user.is_verified():
        return redirect("panel:inicio")
    form = FormularioAcceso(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        ip = ip_cliente(request)
        espera = servicios.segundos_bloqueo(email, ip)
        if espera:
            registrar(request, Accion.LOGIN_BLOQUEADO, f"Bloqueado: {email}")
            form.add_error(None, _mensaje_bloqueo(espera))
        else:
            usuario = authenticate(request, email=email, password=form.cleaned_data["password"])
            if usuario is None:
                servicios.registrar_intento(email, ip, False)
                motivo = "Contraseña incorrecta" if permitidos.esta_permitido(email) else "Correo no permitido"
                registrar(request, Accion.LOGIN_FALLO, f"{motivo}: {email}")
                form.add_error(None, _("Email o contraseña incorrectos."))
            else:
                servicios.registrar_intento(email, ip, True)
                servicios.iniciar_preauth(request, usuario, request.GET.get("next", ""))
                if servicios.tiene_2fa(usuario):
                    return redirect("cuentas:verificar")
                return redirect("cuentas:configurar_2fa")
    return render(request, "cuentas/acceso.html", {"form": form, "alta_habilitada": permitidos.alta_habilitada()})


@vista_publica
@never_cache
@sensitive_post_parameters("password1", "password2", "codigo_alta")
def alta(request):
    """Primer acceso: una persona de CORREOS_PERMITIDOS crea su cuenta con el código de alta."""
    if not permitidos.alta_habilitada():
        raise Http404
    if request.user.is_authenticated and request.user.is_verified():
        return redirect("panel:inicio")
    form = FormularioAlta(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = permitidos.normalizar(form.cleaned_data["email"])
        ip = ip_cliente(request)
        espera = servicios.segundos_bloqueo(email, ip)
        if espera:
            registrar(request, Accion.LOGIN_BLOQUEADO, f"Alta bloqueada: {email}")
            form.add_error(None, _mensaje_bloqueo(espera))
        elif not (
            permitidos.codigo_alta_valido(form.cleaned_data["codigo_alta"])
            and permitidos.esta_permitido(email)
            and not Usuario.objects.filter(email__iexact=email).exists()
        ):
            # Mismo mensaje para código malo, correo no permitido o cuenta ya existente.
            servicios.registrar_intento(email, ip, False)
            registrar(request, Accion.LOGIN_FALLO, f"Alta rechazada: {email}")
            form.add_error(None, _("No se pudo crear la cuenta. Revisa el correo y el código de alta."))
        else:
            nombre = form.cleaned_data["nombre"].strip()
            password = form.cleaned_data["password1"]
            try:
                validate_password(password, Usuario(email=email, nombre=nombre))
            except ValidationError as exc:
                form.add_error("password1", exc)
            else:
                usuario = Usuario.objects.create_user(
                    email=email, password=password, nombre=nombre, rol=permitidos.rol_para(email)
                )
                usuario.backend = servicios.BACKEND
                servicios.registrar_intento(email, ip, True)
                registrar(
                    request, Accion.LOGIN_OK, f"Cuenta creada en el primer acceso ({usuario.rol})", usuario=usuario
                )
                servicios.iniciar_preauth(request, usuario)
                return redirect("cuentas:configurar_2fa")
    return render(request, "cuentas/alta.html", {"form": form})


@vista_publica
@never_cache
def verificar(request):
    usuario = servicios.usuario_preauth(request)
    if usuario is None:
        messages.info(request, _("Tu sesión de acceso caducó. Vuelve a escribir tu contraseña."))
        return redirect("cuentas:login")
    if not servicios.tiene_2fa(usuario):
        return redirect("cuentas:configurar_2fa")

    modo = "recuperacion" if request.GET.get("modo") == "recuperacion" else "totp"
    Formulario = FormularioRecuperacion if modo == "recuperacion" else FormularioCodigo
    form = Formulario(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ip = ip_cliente(request)
        espera = servicios.segundos_bloqueo(usuario.email, ip)
        if espera:
            registrar(request, Accion.LOGIN_BLOQUEADO, "Bloqueado en 2FA", usuario=usuario)
            form.add_error(None, _mensaje_bloqueo(espera))
        else:
            if modo == "recuperacion":
                dispositivo = DispositivoRecuperacion.objects.filter(user=usuario).first()
            else:
                dispositivo = servicios.dispositivo_totp(usuario)
            if dispositivo and dispositivo.verify_token(form.cleaned_data["codigo"]):
                servicios.registrar_intento(usuario.email, ip, True, IntentoAcceso.Fase.DOSFA)
                siguiente = servicios.completar_login(request, usuario, dispositivo)
                registrar(request, Accion.LOGIN_OK, "Acceso con 2FA")
                if modo == "recuperacion":
                    restantes = dispositivo.restantes
                    registrar(request, Accion.CODIGO_RECUPERACION, f"Quedan {restantes}")
                    messages.warning(
                        request,
                        _(
                            "Has usado un código de recuperación. Te quedan %(restantes)s. Si perdiste el móvil, reconfigura la app autenticadora en Mi cuenta."
                        )
                        % {"restantes": restantes},
                    )
                return redirect(_siguiente_seguro(request, siguiente))
            servicios.registrar_intento(usuario.email, ip, False, IntentoAcceso.Fase.DOSFA)
            registrar(request, Accion.DOSFA_FALLO, "Código incorrecto", usuario=usuario)
            form.add_error(
                None, _("Código incorrecto o caducado. Si fallas varias veces tendrás que esperar unos segundos.")
            )
    return render(request, "cuentas/verificar.html", {"form": form, "modo": modo, "usuario_preauth": usuario})


@vista_publica
@never_cache
def configurar_2fa(request):
    """Alta obligatoria de la app autenticadora (primer acceso) o reconfiguración."""
    reconfigurando = request.user.is_authenticated and request.user.is_verified()
    if reconfigurando:
        marca = request.session.get(CLAVE_RECONFIGURAR, 0)
        if time.time() - marca > 300:
            messages.info(request, _("Confirma primero tu código actual."))
            return redirect("cuentas:cuenta")
        usuario = request.user
    else:
        usuario = servicios.usuario_preauth(request)
        if usuario is None:
            return redirect("cuentas:login")
        if servicios.tiene_2fa(usuario):
            return redirect("cuentas:verificar")

    from django_otp.plugins.otp_totp.models import TOTPDevice

    dispositivo = None
    pk = request.session.get(CLAVE_DISPOSITIVO_NUEVO)
    if pk:
        dispositivo = TOTPDevice.objects.filter(pk=pk, user=usuario, confirmed=False).first()
    if dispositivo is None:
        dispositivo = servicios.nuevo_dispositivo_totp(usuario)
        request.session[CLAVE_DISPOSITIVO_NUEVO] = dispositivo.pk

    form = FormularioCodigo(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if dispositivo.verify_token(form.cleaned_data["codigo"]):
            servicios.confirmar_dispositivo(dispositivo)
            request.session.pop(CLAVE_DISPOSITIVO_NUEVO, None)
            request.session.pop(CLAVE_RECONFIGURAR, None)
            codigos = servicios.generar_codigos_recuperacion(usuario)
            if reconfigurando:
                otp_login(request, dispositivo)
            else:
                servicios.completar_login(request, usuario, dispositivo)
            request.session[servicios.CLAVE_CODIGOS] = codigos
            registrar(request, Accion.DOSFA_ACTIVADA, "App autenticadora configurada", usuario=usuario)
            return redirect("cuentas:codigos")
        form.add_error("codigo", _("Ese código no coincide. Comprueba que la hora del móvil es automática."))

    return render(
        request,
        "cuentas/configurar_2fa.html",
        {
            "form": form,
            "qr": servicios.qr_svg(dispositivo.config_url),
            "clave": servicios.clave_legible(dispositivo),
            "reconfigurando": reconfigurando,
        },
    )


@never_cache
def codigos(request):
    codigos = request.session.get(servicios.CLAVE_CODIGOS)
    if not codigos:
        return redirect("cuentas:cuenta")
    if request.method == "POST":
        request.session.pop(servicios.CLAVE_CODIGOS, None)
        messages.success(request, _("Listo. Guarda esos códigos en un lugar seguro."))
        return redirect("panel:inicio")
    return render(request, "cuentas/codigos.html", {"codigos": codigos})


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
    confirmar = FormularioCodigo()

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
        elif accion in ("regenerar", "reconfigurar"):
            confirmar = FormularioCodigo(request.POST)
            dispositivo = servicios.dispositivo_totp(request.user)
            if confirmar.is_valid() and dispositivo and dispositivo.verify_token(confirmar.cleaned_data["codigo"]):
                if accion == "regenerar":
                    request.session[servicios.CLAVE_CODIGOS] = servicios.generar_codigos_recuperacion(request.user)
                    registrar(request, Accion.CODIGOS_REGENERADOS)
                    return redirect("cuentas:codigos")
                request.session[CLAVE_RECONFIGURAR] = time.time()
                request.session.pop(CLAVE_DISPOSITIVO_NUEVO, None)
                return redirect("cuentas:configurar_2fa")
            if confirmar.is_valid():
                confirmar.add_error("codigo", _("Código incorrecto."))

    confirmar.fields["codigo"].widget.attrs.pop("autofocus", None)
    return render(
        request,
        "cuentas/cuenta.html",
        {
            "perfil": perfil,
            "password": password,
            "confirmar": confirmar,
            "restantes": servicios.codigos_restantes(request.user),
        },
    )
