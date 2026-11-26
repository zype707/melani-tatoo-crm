import os
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import IntentoAcceso, Usuario, normalizar_usuario

# Variables de entorno para crear la cuenta de la propietaria al desplegar (ver crear_cuenta --desde-entorno).
ENV_USUARIO = "PROPIETARIA_USUARIO"
ENV_PASSWORD = "PROPIETARIA_PASSWORD"  # noqa: S105 - nombre de la variable, no una contraseña
ENV_NOMBRE = "PROPIETARIA_NOMBRE"


# --- Cuentas ---------------------------------------------------------------------------------


def crear_cuenta(usuario: str, password: str, nombre: str = "", rol: str = Usuario.Rol.PROPIETARIA) -> Usuario:
    """Crea una cuenta validando la contraseña. Lanza ValueError si el usuario ya existe
    y ValidationError si la contraseña no cumple los requisitos."""
    usuario = normalizar_usuario(usuario)
    if Usuario.objects.filter(usuario__iexact=usuario).exists():
        raise ValueError(f"Ya existe una cuenta con el usuario «{usuario}».")
    nombre = (nombre or "").strip() or usuario.split("@")[0].capitalize()
    cuenta = Usuario(usuario=usuario, nombre=nombre, rol=rol)
    cuenta.full_clean(exclude=["password"])
    validate_password(password, cuenta)
    return Usuario.objects.create_user(usuario=usuario, password=password, nombre=nombre, rol=rol)


def usuario_desde_email(email: str, ocupados: set[str], respaldo: str = "usuaria") -> str:
    """Nombre de usuario a partir de un email (lo de antes de la @), sin repetir ninguno de ``ocupados``.

    Lo usan la migración que pasó del acceso por email al acceso por usuario y la
    restauración de copias de seguridad anteriores a ese cambio.
    """
    base = re.sub(r"[^\w.@+-]", "", normalizar_usuario((email or "").split("@")[0]))[:140] or respaldo
    candidato, n = base, 2
    while candidato in ocupados:
        candidato, n = f"{base}{n}", n + 1
    ocupados.add(candidato)
    return candidato


def datos_cuenta_inicial() -> dict:
    """Usuario, contraseña y nombre de la propietaria definidos por variables de entorno."""
    return {
        "usuario": normalizar_usuario(os.environ.get(ENV_USUARIO)),
        "password": os.environ.get(ENV_PASSWORD, ""),
        "nombre": (os.environ.get(ENV_NOMBRE) or "").strip(),
    }


# --- Bloqueo por intentos ---------------------------------------------------------------


def registrar_intento(usuario: str, ip: str | None, exito: bool):
    IntentoAcceso.objects.create(usuario=normalizar_usuario(usuario)[:150], ip=ip, exito=exito)


def segundos_bloqueo(usuario: str, ip: str | None) -> int:
    """0 si se puede intentar; si no, segundos que faltan para desbloquear."""
    ahora = timezone.now()
    usuario = normalizar_usuario(usuario)
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
        IntentoAcceso.objects.filter(usuario=usuario, ip=ip, exito=True)
        .order_by("-creado_en")
        .values_list("creado_en", flat=True)
        .first()
    )
    return max(
        restante(fallos.filter(usuario=usuario, ip=ip), settings.ACCESO_MAX_FALLOS_USUARIO_IP, ventana, ultimo_exito),
        restante(fallos.filter(ip=ip), settings.ACCESO_MAX_FALLOS_IP, hora) if ip else 0,
        restante(fallos.filter(usuario=usuario), settings.ACCESO_MAX_FALLOS_USUARIO, hora),
    )
