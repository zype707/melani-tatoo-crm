import re
import secrets
import time
from base64 import b32encode
from datetime import timedelta

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import CodigoRecuperacion, DispositivoRecuperacion, IntentoAcceso, Usuario
from .permitidos import esta_permitido

ALFABETO = "abcdefghjkmnpqrstuvwxyz23456789"  # sin 0/o, 1/l/i
NUM_CODIGOS = 8
CLAVE_PREAUTH = "_preauth"
CLAVE_CODIGOS = "_codigos_nuevos"
BACKEND = "apps.cuentas.backends.BackendCorreosPermitidos"


# --- Códigos de recuperación -----------------------------------------------------


def normalizar_codigo(texto: str) -> str:
    limpio = re.sub(r"[\s-]", "", texto or "").lower()
    return limpio if re.fullmatch(f"[{ALFABETO}]{{10}}", limpio) else ""


def generar_codigos_recuperacion(usuario: Usuario) -> list[str]:
    """Sustituye los códigos anteriores por 8 nuevos. Devuelve los códigos en claro
    (solo existen en este momento: en BD se guarda su hash)."""
    codigos = ["".join(secrets.choice(ALFABETO) for _ in range(10)) for _ in range(NUM_CODIGOS)]
    with transaction.atomic():
        dispositivo, _ = DispositivoRecuperacion.objects.get_or_create(
            user=usuario, defaults={"name": "Códigos de recuperación", "confirmed": True}
        )
        dispositivo.codigos.all().delete()
        dispositivo.throttle_reset()
        CodigoRecuperacion.objects.bulk_create(
            CodigoRecuperacion(dispositivo=dispositivo, codigo_hash=make_password(c)) for c in codigos
        )
    return [f"{c[:5]}-{c[5:]}" for c in codigos]


def codigos_restantes(usuario: Usuario) -> int:
    dispositivo = DispositivoRecuperacion.objects.filter(user=usuario).first()
    return dispositivo.restantes if dispositivo else 0


# --- TOTP --------------------------------------------------------------------------


def dispositivo_totp(usuario: Usuario) -> TOTPDevice | None:
    return TOTPDevice.objects.filter(user=usuario, confirmed=True).first()


def tiene_2fa(usuario: Usuario) -> bool:
    return TOTPDevice.objects.filter(user=usuario, confirmed=True).exists()


def nuevo_dispositivo_totp(usuario: Usuario) -> TOTPDevice:
    TOTPDevice.objects.filter(user=usuario, confirmed=False).delete()
    return TOTPDevice.objects.create(user=usuario, name="App autenticadora", confirmed=False)


def confirmar_dispositivo(dispositivo: TOTPDevice) -> None:
    with transaction.atomic():
        TOTPDevice.objects.filter(user=dispositivo.user).exclude(pk=dispositivo.pk).delete()
        dispositivo.confirmed = True
        dispositivo.save(update_fields=["confirmed"])


def clave_legible(dispositivo: TOTPDevice) -> str:
    clave = b32encode(dispositivo.bin_key).decode().rstrip("=")
    return " ".join(clave[i : i + 4] for i in range(0, len(clave), 4))


def qr_svg(texto: str) -> str:
    imagen = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    svg = imagen.to_string(encoding="unicode")
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)


# --- Bloqueo por intentos ---------------------------------------------------------------


def registrar_intento(email: str, ip: str | None, exito: bool, fase: str = IntentoAcceso.Fase.PASSWORD):
    IntentoAcceso.objects.create(email=(email or "")[:254].lower(), ip=ip, exito=exito, fase=fase)


def segundos_bloqueo(email: str, ip: str | None) -> int:
    """0 si se puede intentar; si no, segundos que faltan para desbloquear."""
    ahora = timezone.now()
    email = (email or "").lower()
    ventana = timedelta(minutes=settings.ACCESO_VENTANA_MINUTOS)
    hora = timedelta(hours=1)
    fallos = IntentoAcceso.objects.filter(exito=False)

    def restante(qs, limite, duracion, desde=None):
        inicio = max(ahora - duracion, desde) if desde else ahora - duracion
        recientes = qs.filter(creado_en__gte=inicio)
        if recientes.count() < limite:
            return 0
        ultimo = recientes.order_by("-creado_en").first().creado_en
        return max(0, int((ultimo + duracion - ahora).total_seconds()))

    ultimo_exito = (
        IntentoAcceso.objects.filter(email=email, ip=ip, exito=True)
        .order_by("-creado_en")
        .values_list("creado_en", flat=True)
        .first()
    )
    return max(
        restante(fallos.filter(email=email, ip=ip), settings.ACCESO_MAX_FALLOS_EMAIL_IP, ventana, ultimo_exito),
        restante(fallos.filter(ip=ip), settings.ACCESO_MAX_FALLOS_IP, hora) if ip else 0,
        restante(fallos.filter(email=email), settings.ACCESO_MAX_FALLOS_EMAIL, hora),
    )


# --- Sesión en dos pasos -----------------------------------------------------------------


def iniciar_preauth(request, usuario: Usuario, siguiente: str = "") -> None:
    """Contraseña correcta, falta el segundo factor: la sesión NO está autenticada aún."""
    request.session.cycle_key()
    request.session[CLAVE_PREAUTH] = {
        "uid": usuario.pk,
        "ts": time.time(),
        "backend": getattr(usuario, "backend", BACKEND),
        "next": siguiente,
    }


def usuario_preauth(request) -> Usuario | None:
    datos = request.session.get(CLAVE_PREAUTH)
    if not datos:
        return None
    if time.time() - datos.get("ts", 0) > settings.ACCESO_PREAUTH_MINUTOS * 60:
        request.session.pop(CLAVE_PREAUTH, None)
        return None
    usuario = Usuario.objects.filter(pk=datos["uid"], is_active=True).first()
    if usuario is None or not esta_permitido(usuario.email):
        request.session.pop(CLAVE_PREAUTH, None)
        return None
    return usuario


def completar_login(request, usuario: Usuario, dispositivo) -> str:
    datos = request.session.pop(CLAVE_PREAUTH, {}) or {}
    login(request, usuario, backend=datos.get("backend"))
    otp_login(request, dispositivo)
    return datos.get("next") or ""
