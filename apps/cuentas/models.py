from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from django_otp.models import Device, ThrottlingMixin


class GestorUsuarios(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._crear(email, password, **extra)

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        PROPIETARIA = "propietaria", "Propietaria"
        AYUDANTE = "ayudante", "Ayudante"

    email = models.EmailField("Email", unique=True)
    nombre = models.CharField("Nombre", max_length=120)
    rol = models.CharField("Rol", max_length=16, choices=Rol.choices, default=Rol.PROPIETARIA)
    is_active = models.BooleanField("Activa", default=True)
    is_staff = models.BooleanField(default=False)
    fecha_alta = models.DateTimeField(default=timezone.now)

    objects = GestorUsuarios()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        verbose_name = "usuaria"
        constraints = [models.UniqueConstraint(Lower("email"), name="usuario_email_unico_ci")]

    def __str__(self):
        return self.nombre or self.email

    @property
    def es_propietaria(self) -> bool:
        return self.rol == self.Rol.PROPIETARIA

    @property
    def primer_nombre(self) -> str:
        return (self.nombre or self.email).split()[0]


class DispositivoRecuperacion(ThrottlingMixin, Device):
    """Códigos de recuperación de un solo uso integrados en django-otp.

    Los códigos se guardan con hash Argon2 (el plugin estático de django-otp
    los guarda en claro, por eso no se usa).
    """

    class Meta:
        verbose_name = "códigos de recuperación"

    def get_throttle_factor(self):
        return 1

    @property
    def restantes(self) -> int:
        return self.codigos.filter(usado_en__isnull=True).count()

    def verify_token(self, token):
        from .servicios import normalizar_codigo

        permitido, _ = self.verify_is_allowed()
        if not permitido:
            return False
        normal = normalizar_codigo(token)
        if normal:
            with transaction.atomic():
                for codigo in self.codigos.select_for_update().filter(usado_en__isnull=True):
                    if check_password(normal, codigo.codigo_hash):
                        codigo.usado_en = timezone.now()
                        codigo.save(update_fields=["usado_en"])
                        self.throttle_reset()
                        return True
        self.throttle_increment()
        return False


class CodigoRecuperacion(models.Model):
    dispositivo = models.ForeignKey(DispositivoRecuperacion, on_delete=models.CASCADE, related_name="codigos")
    codigo_hash = models.CharField(max_length=255)
    creado_en = models.DateTimeField(auto_now_add=True)
    usado_en = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Código {'usado' if self.usado_en else 'disponible'}"


class IntentoAcceso(models.Model):
    class Fase(models.TextChoices):
        PASSWORD = "password", "Contraseña"
        DOSFA = "2fa", "Segundo factor"

    email = models.CharField(max_length=254)
    ip = models.GenericIPAddressField(null=True, blank=True)
    exito = models.BooleanField(default=False)
    fase = models.CharField(max_length=10, choices=Fase.choices, default=Fase.PASSWORD)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["email", "creado_en"]),
            models.Index(fields=["ip", "creado_en"]),
        ]

    def __str__(self):
        return f"{self.email} · {'ok' if self.exito else 'fallo'} · {self.creado_en:%Y-%m-%d %H:%M}"
