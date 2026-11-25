from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Metodo(models.TextChoices):
    EFECTIVO = "efectivo", _("Efectivo")
    TARJETA = "tarjeta", _("Tarjeta")
    ZELLE = "zelle", _("Zelle")
    VENMO = "venmo", _("Venmo")
    CASH_APP = "cash_app", _("Cash App")
    PAYPAL = "paypal", _("PayPal")
    TRANSFERENCIA = "transferencia", _("Transferencia")
    OTRO = "otro", _("Otro")


class Pago(models.Model):
    """Ingreso: señas, sesiones, flash o productos. Registro manual, sin pasarela."""

    class Tipo(models.TextChoices):
        SENA = "sena", _("Seña / depósito")
        SESION = "sesion", _("Sesión")
        FLASH = "flash", _("Flash")
        PRODUCTO = "producto", _("Producto (cremas…)")
        OTRO = "otro", _("Otro")

    cliente = models.ForeignKey(
        "clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos"
    )
    cita = models.ForeignKey("agenda.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos")
    tatuaje = models.ForeignKey(
        "clientes.Tatuaje", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos"
    )
    tipo = models.CharField(_("Concepto"), max_length=10, choices=Tipo.choices, default=Tipo.SESION)
    metodo = models.CharField(_("Método"), max_length=14, choices=Metodo.choices, default=Metodo.EFECTIVO)
    importe = models.DecimalField(_("Importe"), max_digits=10, decimal_places=2)
    fecha = models.DateField(_("Fecha"), default=timezone.localdate)
    notas = models.CharField(_("Notas"), max_length=200, blank=True)
    devuelto = models.BooleanField(_("Devuelto"), default=False)
    devuelto_en = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-creado_en"]
        indexes = [models.Index(fields=["fecha"]), models.Index(fields=["tipo", "fecha"])]
        constraints = [models.CheckConstraint(condition=Q(importe__gt=0), name="pago_importe_positivo")]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.importe}"


class Gasto(models.Model):
    class Categoria(models.TextChoices):
        MATERIAL = "material", _("Material (agujas, tintas, film…)")
        ALQUILER = "alquiler", _("Alquiler")
        SUMINISTROS = "suministros", _("Luz, agua, internet")
        LICENCIAS = "licencias", _("Licencias y permisos")
        EQUIPO = "equipo", _("Equipo")
        MARKETING = "marketing", _("Marketing")
        FORMACION = "formacion", _("Formación")
        GESTORIA = "gestoria", _("Gestoría / impuestos")
        OTROS = "otros", _("Otros")

    fecha = models.DateField(_("Fecha"), default=timezone.localdate)
    categoria = models.CharField(_("Categoría"), max_length=12, choices=Categoria.choices, default=Categoria.MATERIAL)
    concepto = models.CharField(_("Concepto"), max_length=160)
    importe = models.DecimalField(_("Importe"), max_digits=10, decimal_places=2)
    metodo = models.CharField(_("Método"), max_length=14, choices=Metodo.choices, default=Metodo.TARJETA)
    notas = models.CharField(_("Notas"), max_length=200, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-creado_en"]
        indexes = [models.Index(fields=["fecha"])]
        constraints = [models.CheckConstraint(condition=Q(importe__gt=0), name="gasto_importe_positivo")]

    def __str__(self):
        return f"{self.concepto} {self.importe}"
