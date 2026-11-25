from django.db import models
from django.db.models import Q
from django.utils import timezone


class Metodo(models.TextChoices):
    EFECTIVO = "efectivo", "Efectivo"
    TARJETA = "tarjeta", "Tarjeta"
    ZELLE = "zelle", "Zelle"
    VENMO = "venmo", "Venmo"
    CASH_APP = "cash_app", "Cash App"
    PAYPAL = "paypal", "PayPal"
    TRANSFERENCIA = "transferencia", "Transferencia"
    OTRO = "otro", "Otro"


class Pago(models.Model):
    """Ingreso: señas, sesiones, flash o productos. Registro manual, sin pasarela."""

    class Tipo(models.TextChoices):
        SENA = "sena", "Seña / depósito"
        SESION = "sesion", "Sesión"
        FLASH = "flash", "Flash"
        PRODUCTO = "producto", "Producto (cremas…)"
        OTRO = "otro", "Otro"

    cliente = models.ForeignKey(
        "clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos"
    )
    cita = models.ForeignKey("agenda.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos")
    tatuaje = models.ForeignKey(
        "clientes.Tatuaje", null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos"
    )
    tipo = models.CharField("Concepto", max_length=10, choices=Tipo.choices, default=Tipo.SESION)
    metodo = models.CharField("Método", max_length=14, choices=Metodo.choices, default=Metodo.EFECTIVO)
    importe = models.DecimalField("Importe", max_digits=10, decimal_places=2)
    fecha = models.DateField("Fecha", default=timezone.localdate)
    notas = models.CharField("Notas", max_length=200, blank=True)
    devuelto = models.BooleanField("Devuelto", default=False)
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
        MATERIAL = "material", "Material (agujas, tintas, film…)"
        ALQUILER = "alquiler", "Alquiler"
        SUMINISTROS = "suministros", "Luz, agua, internet"
        LICENCIAS = "licencias", "Licencias y permisos"
        EQUIPO = "equipo", "Equipo"
        MARKETING = "marketing", "Marketing"
        FORMACION = "formacion", "Formación"
        GESTORIA = "gestoria", "Gestoría / impuestos"
        OTROS = "otros", "Otros"

    fecha = models.DateField("Fecha", default=timezone.localdate)
    categoria = models.CharField("Categoría", max_length=12, choices=Categoria.choices, default=Categoria.MATERIAL)
    concepto = models.CharField("Concepto", max_length=160)
    importe = models.DecimalField("Importe", max_digits=10, decimal_places=2)
    metodo = models.CharField("Método", max_length=14, choices=Metodo.choices, default=Metodo.TARJETA)
    notas = models.CharField("Notas", max_length=200, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-creado_en"]
        indexes = [models.Index(fields=["fecha"])]
        constraints = [models.CheckConstraint(condition=Q(importe__gt=0), name="gasto_importe_positivo")]

    def __str__(self):
        return f"{self.concepto} {self.importe}"
