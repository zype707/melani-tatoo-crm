from django.conf import settings
from django.db import models
from django.utils import timezone


class UsoIA(models.Model):
    """Una llamada a la IA. Solo métricas: nunca se guarda lo enviado ni lo recibido."""

    class Funcion(models.TextChoices):
        REDACTAR = "redactar", "Redactar mensaje"
        TRIAJE = "triaje", "Triaje de solicitud"
        RESUMEN = "resumen", "Resumen previo a la cita"
        RETENCION = "retencion", "Sugerencias de retención"
        BUSQUEDA = "busqueda", "Búsqueda en lenguaje natural"
        RESPUESTA = "respuesta", "Respuesta sugerida"

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
        verbose_name = "uso de IA"
        verbose_name_plural = "usos de IA"

    def __str__(self):
        return f"{self.get_funcion_display()} · {'ok' if self.exito else self.error}"
