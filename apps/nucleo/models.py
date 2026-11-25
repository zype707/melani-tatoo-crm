from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import textos


class AjustesEstudio(models.Model):
    """Configuración única del estudio (siempre pk=1)."""

    # Marca y contacto
    nombre = models.CharField(_("Nombre del estudio"), max_length=120, default="Mi estudio")
    nombre_artista = models.CharField(_("Nombre de la artista"), max_length=120, blank=True)
    eslogan = models.CharField(_("Frase corta"), max_length=160, blank=True)
    logo = models.ImageField(_("Logotipo"), upload_to="marca/", blank=True)
    telefono = models.CharField(_("Teléfono"), max_length=32, blank=True)
    email = models.EmailField(_("Email"), blank=True)
    direccion = models.CharField(_("Dirección"), max_length=255, blank=True)
    instagram = models.CharField(_("Instagram"), max_length=60, blank=True, help_text=_("Sin @"))
    web = models.URLField(_("Web"), blank=True)

    # Regional (moneda y zona horaria se configuran por variable de entorno)
    edad_minima = models.PositiveSmallIntegerField(_("Edad mínima"), default=18)

    # Textos legales y de cuidados
    texto_consentimiento = models.TextField(
        _("Texto del consentimiento informado"), default=textos.TEXTO_CONSENTIMIENTO
    )
    version_consentimiento = models.PositiveIntegerField(default=1, editable=False)
    texto_privacidad = models.TextField(_("Aviso de privacidad"), default=textos.TEXTO_PRIVACIDAD)
    politica_senas = models.TextField(_("Política de señas y cancelación"), default=textos.POLITICA_SENAS)
    texto_cuidados = models.TextField(_("Cuidados generales"), default=textos.TEXTO_CUIDADOS)
    retencion_consentimientos_anios = models.PositiveSmallIntegerField(
        _("Años de conservación de consentimientos"),
        default=2,
        help_text=_("Florida exige conservar los registros de clientes 2 años (FAC 64E-28.007)."),
    )

    # Reservas y flash públicos
    reservas_activas = models.BooleanField(_("Aceptar solicitudes de reserva"), default=True)
    reserva_bienvenida = models.TextField(_("Texto de bienvenida"), default=textos.RESERVA_BIENVENIDA)
    flash_publico = models.BooleanField(_("Publicar catálogo de flash"), default=False)

    # Retención
    meses_inactividad = models.PositiveSmallIntegerField(_("Meses sin volver para considerar inactivo"), default=6)
    reactivaciones_por_dia = models.PositiveSmallIntegerField(_("Reactivaciones por día"), default=3)
    campana_por_dia = models.PositiveSmallIntegerField(_("Mensajes de campaña por día"), default=10)
    umbral_vip = models.DecimalField(_("Gasto acumulado para VIP"), max_digits=10, decimal_places=2, default=1500)
    recordatorio_dias_antes = models.PositiveSmallIntegerField(_("Recordar cita con (días)"), default=1)

    # IA
    ia_activa = models.BooleanField(_("Usar asistente de IA"), default=True)
    ia_tono = models.TextField(_("Tono de voz"), default=textos.IA_TONO, blank=True)
    ia_ejemplos = models.TextField(
        _("Ejemplos de mensajes tuyos"),
        blank=True,
        help_text=_("Pega 3-5 mensajes reales tuyos (sin datos de clientes) para imitar tu estilo."),
    )
    ia_limite_mensual = models.PositiveIntegerField(
        _("Límite mensual de consultas"), null=True, blank=True, help_text=_("Vacío = valor del servidor.")
    )

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("ajustes del estudio")
        verbose_name_plural = _("ajustes del estudio")

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls) -> "AjustesEstudio":
        obj, creado = cls.objects.get_or_create(pk=1)
        if creado and settings.LANGUAGE_CODE.startswith("en"):
            # Textos de partida en el idioma del estudio (el modelo trae los de español por defecto).
            from . import textos_en

            for campo, texto in textos_en.POR_CAMPO.items():
                setattr(obj, campo, texto)
            obj.nombre = "My studio"
            obj.save()
        return obj

    @property
    def limite_ia(self) -> int:
        return self.ia_limite_mensual or settings.IA_LIMITE_MENSUAL

    @property
    def firma(self) -> str:
        return self.nombre_artista or self.nombre


class RegistroAuditoria(models.Model):
    class Accion(models.TextChoices):
        LOGIN_OK = "login_ok", _("Inicio de sesión")
        LOGIN_FALLO = "login_fallo", _("Intento fallido")
        LOGIN_BLOQUEADO = "login_bloqueado", _("Acceso bloqueado")
        LOGOUT = "logout", _("Cierre de sesión")
        DOSFA_ACTIVADA = "2fa_activada", _("2FA activada")
        DOSFA_FALLO = "2fa_fallo", _("Código 2FA incorrecto")
        CODIGO_RECUPERACION = "codigo_recuperacion", _("Código de recuperación usado")
        CODIGOS_REGENERADOS = "codigos_regenerados", _("Códigos regenerados")
        PASSWORD_CAMBIADA = "password_cambiada", _("Contraseña cambiada")
        EXPORTACION = "exportacion", _("Exportación de datos")
        BORRADO = "borrado", _("Borrado")
        ANONIMIZACION = "anonimizacion", _("Anonimización")
        ACCESO_DOCUMENTO = "acceso_documento", _("Acceso a documento sensible")
        AJUSTES = "ajustes", _("Cambio de ajustes")
        CONSENTIMIENTO = "consentimiento", _("Consentimiento")
        TAREA = "tarea", _("Tarea programada")
        IA = "ia", _("Consulta de IA")

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    accion = models.CharField(max_length=32, choices=Accion.choices)
    descripcion = models.CharField(max_length=255, blank=True)
    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["accion", "-creado_en"])]
        verbose_name = _("registro de auditoría")

    def __str__(self):
        return f"{self.get_accion_display()} · {self.creado_en:%Y-%m-%d %H:%M}"


class EnlacePublico(models.Model):
    """Token de acceso a una página pública.

    El token nunca se guarda en claro salvo en los enlaces que el estudio
    publica por diseño (reserva y catálogo). Para los enlaces de un cliente
    concreto (cita) solo se guarda su SHA-256.
    """

    class Proposito(models.TextChoices):
        RESERVA = "reserva", _("Solicitud de reserva")
        CATALOGO = "catalogo", _("Catálogo de flash")
        CITA = "cita", _("Gestión de cita")

    proposito = models.CharField(max_length=16, choices=Proposito.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    token_visible = models.CharField(max_length=64, blank=True)
    objeto_id = models.PositiveBigIntegerField(null=True, blank=True)
    caduca_en = models.DateTimeField()
    revocado_en = models.DateTimeField(null=True, blank=True)
    usos = models.PositiveIntegerField(default=0)
    ultimo_uso_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["proposito", "objeto_id"]),
            models.Index(fields=["caduca_en"]),
        ]

    def __str__(self):
        return f"{self.get_proposito_display()} (caduca {self.caduca_en:%Y-%m-%d})"

    @property
    def vigente(self) -> bool:
        return self.revocado_en is None and self.caduca_en > timezone.now()
