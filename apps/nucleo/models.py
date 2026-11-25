from django.conf import settings
from django.db import models
from django.utils import timezone

from . import textos


class AjustesEstudio(models.Model):
    """Configuración única del estudio (siempre pk=1)."""

    # Marca y contacto
    nombre = models.CharField("Nombre del estudio", max_length=120, default="Mi estudio")
    nombre_artista = models.CharField("Nombre de la artista", max_length=120, blank=True)
    eslogan = models.CharField("Frase corta", max_length=160, blank=True)
    logo = models.ImageField("Logotipo", upload_to="marca/", blank=True)
    telefono = models.CharField("Teléfono", max_length=32, blank=True)
    email = models.EmailField("Email", blank=True)
    direccion = models.CharField("Dirección", max_length=255, blank=True)
    instagram = models.CharField("Instagram", max_length=60, blank=True, help_text="Sin @")
    web = models.URLField("Web", blank=True)

    # Regional (moneda y zona horaria se configuran por variable de entorno)
    edad_minima = models.PositiveSmallIntegerField("Edad mínima", default=18)

    # Textos legales y de cuidados
    texto_consentimiento = models.TextField("Texto del consentimiento informado", default=textos.TEXTO_CONSENTIMIENTO)
    version_consentimiento = models.PositiveIntegerField(default=1, editable=False)
    texto_privacidad = models.TextField("Aviso de privacidad", default=textos.TEXTO_PRIVACIDAD)
    politica_senas = models.TextField("Política de señas y cancelación", default=textos.POLITICA_SENAS)
    texto_cuidados = models.TextField("Cuidados generales", default=textos.TEXTO_CUIDADOS)
    retencion_consentimientos_anios = models.PositiveSmallIntegerField(
        "Años de conservación de consentimientos",
        default=2,
        help_text="Florida exige conservar los registros de clientes 2 años (FAC 64E-28.007).",
    )

    # Reservas y flash públicos
    reservas_activas = models.BooleanField("Aceptar solicitudes de reserva", default=True)
    reserva_bienvenida = models.TextField("Texto de bienvenida", default=textos.RESERVA_BIENVENIDA)
    flash_publico = models.BooleanField("Publicar catálogo de flash", default=False)

    # Retención
    meses_inactividad = models.PositiveSmallIntegerField("Meses sin volver para considerar inactivo", default=6)
    reactivaciones_por_dia = models.PositiveSmallIntegerField("Reactivaciones por día", default=3)
    campana_por_dia = models.PositiveSmallIntegerField("Mensajes de campaña por día", default=10)
    umbral_vip = models.DecimalField("Gasto acumulado para VIP", max_digits=10, decimal_places=2, default=1500)
    recordatorio_dias_antes = models.PositiveSmallIntegerField("Recordar cita con (días)", default=1)

    # IA
    ia_activa = models.BooleanField("Usar asistente de IA", default=True)
    ia_tono = models.TextField("Tono de voz", default=textos.IA_TONO, blank=True)
    ia_ejemplos = models.TextField(
        "Ejemplos de mensajes tuyos",
        blank=True,
        help_text="Pega 3-5 mensajes reales tuyos (sin datos de clientes) para imitar tu estilo.",
    )
    ia_limite_mensual = models.PositiveIntegerField(
        "Límite mensual de consultas", null=True, blank=True, help_text="Vacío = valor del servidor."
    )

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ajustes del estudio"
        verbose_name_plural = "ajustes del estudio"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls) -> "AjustesEstudio":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def limite_ia(self) -> int:
        return self.ia_limite_mensual or settings.IA_LIMITE_MENSUAL

    @property
    def firma(self) -> str:
        return self.nombre_artista or self.nombre


class RegistroAuditoria(models.Model):
    class Accion(models.TextChoices):
        LOGIN_OK = "login_ok", "Inicio de sesión"
        LOGIN_FALLO = "login_fallo", "Intento fallido"
        LOGIN_BLOQUEADO = "login_bloqueado", "Acceso bloqueado"
        LOGOUT = "logout", "Cierre de sesión"
        DOSFA_ACTIVADA = "2fa_activada", "2FA activada"
        DOSFA_FALLO = "2fa_fallo", "Código 2FA incorrecto"
        CODIGO_RECUPERACION = "codigo_recuperacion", "Código de recuperación usado"
        CODIGOS_REGENERADOS = "codigos_regenerados", "Códigos regenerados"
        PASSWORD_CAMBIADA = "password_cambiada", "Contraseña cambiada"
        EXPORTACION = "exportacion", "Exportación de datos"
        BORRADO = "borrado", "Borrado"
        ANONIMIZACION = "anonimizacion", "Anonimización"
        ACCESO_DOCUMENTO = "acceso_documento", "Acceso a documento sensible"
        AJUSTES = "ajustes", "Cambio de ajustes"
        CONSENTIMIENTO = "consentimiento", "Consentimiento"
        TAREA = "tarea", "Tarea programada"
        IA = "ia", "Consulta de IA"

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
        verbose_name = "registro de auditoría"

    def __str__(self):
        return f"{self.get_accion_display()} · {self.creado_en:%Y-%m-%d %H:%M}"


class EnlacePublico(models.Model):
    """Token de acceso a una página pública.

    El token nunca se guarda en claro salvo en los enlaces que el estudio
    publica por diseño (reserva y catálogo). Para los enlaces de un cliente
    concreto (cita) solo se guarda su SHA-256.
    """

    class Proposito(models.TextChoices):
        RESERVA = "reserva", "Solicitud de reserva"
        CATALOGO = "catalogo", "Catálogo de flash"
        CITA = "cita", "Gestión de cita"

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
