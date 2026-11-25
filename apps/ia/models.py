from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UsoIA(models.Model):
    """Una llamada a la IA. Solo métricas: nunca se guarda lo enviado ni lo recibido."""

    class Funcion(models.TextChoices):
        REDACTAR = "redactar", _("Redactar mensaje")
        TRIAJE = "triaje", _("Triaje de solicitud")
        RESUMEN = "resumen", _("Resumen previo a la cita")
        RETENCION = "retencion", _("Sugerencias de retención")
        BUSQUEDA = "busqueda", _("Búsqueda en lenguaje natural")
        RESPUESTA = "respuesta", _("Respuesta sugerida")

    funcion = models.CharField(max_length=12, choices=Funcion.choices)
    exito = models.BooleanField(default=False)
    error = models.CharField(max_length=40, blank=True)
    duracion_ms = models.PositiveIntegerField(default=0)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = _("uso de IA")
        verbose_name_plural = _("usos de IA")

    def __str__(self):
        return f"{self.get_funcion_display()} · {'ok' if self.exito else self.error}"
