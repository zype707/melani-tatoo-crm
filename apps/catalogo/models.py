from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.clientes.models import Tatuaje


class DisenoFlash(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "disponible", _("Disponible")
        RESERVADO = "reservado", _("Reservado")
        VENDIDO = "vendido", _("Vendido")

    titulo = models.CharField(_("Título"), max_length=100)
    imagen = models.ImageField(upload_to="privado/flash/%Y/%m/")
    miniatura = models.ImageField(upload_to="privado/flash/%Y/%m/")
    precio = models.DecimalField(_("Precio"), max_digits=8, decimal_places=2, null=True, blank=True)
    tamano = models.CharField(_("Tamaño"), max_length=40, blank=True, help_text=_("Ej.: 8 × 6 cm"))
    zona_sugerida = models.CharField(_("Zona sugerida"), max_length=20, choices=Tatuaje.Zona.choices, blank=True)
    descripcion = models.CharField(_("Descripción"), max_length=300, blank=True)
    estado = models.CharField(_("Estado"), max_length=12, choices=Estado.choices, default=Estado.DISPONIBLE)
    repetible = models.BooleanField(_("Se puede repetir"), default=False, help_text=_("Si no, se tatúa una sola vez."))
    publico = models.BooleanField(_("Mostrar en el catálogo público"), default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["orden", "-creado_en"]
        verbose_name = _("diseño flash")
        verbose_name_plural = _("diseños flash")

    def __str__(self):
        return self.titulo

    @property
    def visible_al_publico(self) -> bool:
        return self.publico and self.estado != self.Estado.VENDIDO
