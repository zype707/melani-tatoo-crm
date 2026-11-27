from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def normalizar_usuario(usuario: str | None) -> str:
    """Los nombres de usuario no distinguen mayúsculas ni espacios alrededor."""
    return (usuario or "").strip().lower()


class GestorUsuarios(BaseUserManager):
    use_in_migrations = True

    def _crear(self, usuario, password, **extra):
        usuario = normalizar_usuario(usuario)
        if not usuario:
            raise ValueError(_("El nombre de usuario es obligatorio."))
        cuenta = self.model(usuario=usuario, **extra)
        cuenta.set_password(password)
        cuenta.save(using=self._db)
        return cuenta

    def create_user(self, usuario, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(usuario, password, **extra)

    def create_superuser(self, usuario, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._crear(usuario, password, **extra)

    def get_by_natural_key(self, username):
        return self.get(usuario__iexact=normalizar_usuario(username))


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        PROPIETARIA = "propietaria", _("Propietaria")
        AYUDANTE = "ayudante", _("Ayudante")

    usuario = models.CharField(
        _("Usuario"),
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator()],
        help_text=_("Letras, números y . _ - @ (sin espacios)."),
    )
    nombre = models.CharField(_("Nombre"), max_length=120)
    rol = models.CharField(_("Rol"), max_length=16, choices=Rol.choices, default=Rol.PROPIETARIA)
    is_active = models.BooleanField(_("Activa"), default=True)
    is_staff = models.BooleanField(default=False)
    fecha_alta = models.DateTimeField(default=timezone.now)
    # Ayuda en pantalla: pistas de cada pantalla y lista de primeros pasos (ver apps/nucleo/ayuda.py)
    ayudas_visibles = models.BooleanField(
        _("Mostrar ayudas en pantalla"),
        default=True,
        help_text=_("Pistas cortas arriba de cada pantalla. Puedes cerrarlas una a una o todas a la vez."),
    )
    ayudas_cerradas = models.JSONField(default=list, blank=True, editable=False)

    objects = GestorUsuarios()

    USERNAME_FIELD = "usuario"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        verbose_name = "usuaria"
        constraints = [models.UniqueConstraint(Lower("usuario"), name="usuario_usuario_unico_ci")]

    def __str__(self):
        return self.nombre or self.usuario

    @property
    def es_propietaria(self) -> bool:
        return self.rol == self.Rol.PROPIETARIA

    @property
    def primer_nombre(self) -> str:
        return (self.nombre or self.usuario).split()[0]

    def ayuda_cerrada(self, clave: str) -> bool:
        return clave in (self.ayudas_cerradas or [])

    def cerrar_ayuda(self, clave: str) -> None:
        if not self.ayuda_cerrada(clave):
            self.ayudas_cerradas = [*(self.ayudas_cerradas or []), clave][-200:]
            self.save(update_fields=["ayudas_cerradas"])

    def abrir_ayuda(self, clave: str) -> None:
        if self.ayuda_cerrada(clave):
            self.ayudas_cerradas = [c for c in self.ayudas_cerradas if c != clave]
            self.save(update_fields=["ayudas_cerradas"])


class IntentoAcceso(models.Model):
    """Cada intento de inicio de sesión, para el bloqueo por fuerza bruta (ver servicios.py)."""

    usuario = models.CharField(max_length=150)
    ip = models.GenericIPAddressField(null=True, blank=True)
    exito = models.BooleanField(default=False)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "creado_en"]),
            models.Index(fields=["ip", "creado_en"]),
        ]

    def __str__(self):
        return f"{self.usuario} · {'ok' if self.exito else 'fallo'} · {self.creado_en:%Y-%m-%d %H:%M}"
