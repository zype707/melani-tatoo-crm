from django.db import models
from django.utils import timezone

from apps.clientes.models import Tatuaje


class DisenoFlash(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        RESERVADO = "reservado", "Reservado"
        VENDIDO = "vendido", "Vendido"

    titulo = models.CharField("Título", max_length=100)
    imagen = models.ImageField(upload_to="privado/flash/%Y/%m/")
    miniatura = models.ImageField(upload_to="privado/flash/%Y/%m/")
    precio = models.DecimalField("Precio", max_digits=8, decimal_places=2, null=True, blank=True)
    tamano = models.CharField("Tamaño", max_length=40, blank=True, help_text="Ej.: 8 × 6 cm")
    zona_sugerida = models.CharField("Zona sugerida", max_length=20, choices=Tatuaje.Zona.choices, blank=True)
    descripcion = models.CharField("Descripción", max_length=300, blank=True)
    estado = models.CharField("Estado", max_length=12, choices=Estado.choices, default=Estado.DISPONIBLE)
    repetible = models.BooleanField("Se puede repetir", default=False, help_text="Si no, se tatúa una sola vez.")
    publico = models.BooleanField("Mostrar en el catálogo público", default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["orden", "-creado_en"]
        verbose_name = "diseño flash"
        verbose_name_plural = "diseños flash"

    def __str__(self):
        return self.titulo

    @property
    def visible_al_publico(self) -> bool:
        return self.publico and self.estado != self.Estado.VENDIDO
