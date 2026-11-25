from datetime import datetime, time, timedelta

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import ArrayField, DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.clientes.models import Cliente, Tatuaje


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class TipoCita(models.Model):
    class Categoria(models.TextChoices):
        CONSULTA = "consulta", _("Consulta")
        SESION = "sesion", _("Sesión de tatuaje")
        RETOQUE = "retoque", _("Retoque")

    class Color(models.TextChoices):
        HUESO = "hueso", _("Hueso")
        MENTA = "menta", _("Menta")
        CIELO = "cielo", _("Cielo")
        LILA = "lila", _("Lila")
        ARENA = "arena", _("Arena")
        ROSA = "rosa", _("Rosa")

    nombre = models.CharField(_("Nombre"), max_length=60)
    categoria = models.CharField(_("Categoría"), max_length=10, choices=Categoria.choices, default=Categoria.SESION)
    duracion_minutos = models.PositiveSmallIntegerField(_("Duración (min)"), default=120)
    color = models.CharField(_("Color"), max_length=10, choices=Color.choices, default=Color.HUESO)
    deposito_sugerido = models.DecimalField(_("Seña sugerida"), max_digits=8, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(_("Activo"), default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = _("tipo de cita")
        verbose_name_plural = _("tipos de cita")

    def __str__(self):
        return self.nombre

    @property
    def genera_cuidados(self) -> bool:
        return self.categoria in (self.Categoria.SESION, self.Categoria.RETOQUE)


class EstadoCita(models.TextChoices):
    SOLICITADA = "solicitada", _("Por confirmar")
    CONFIRMADA = "confirmada", _("Confirmada")
    REALIZADA = "realizada", _("Realizada")
    CANCELADA = "cancelada", _("Cancelada")
    NO_SHOW = "no_show", _("No vino")


ESTADOS_ACTIVOS = [EstadoCita.SOLICITADA, EstadoCita.CONFIRMADA, EstadoCita.REALIZADA]
ESTADOS_PENDIENTES = [EstadoCita.SOLICITADA, EstadoCita.CONFIRMADA]


def limites_dia(fecha):
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    return inicio, inicio + timedelta(days=1)


class CitaQuerySet(models.QuerySet):
    def activas(self):
        return self.filter(estado__in=ESTADOS_ACTIVOS)

    def pendientes(self):
        return self.filter(estado__in=ESTADOS_PENDIENTES)

    def futuras(self):
        return self.pendientes().filter(inicio__gte=timezone.now())

    def entre(self, desde, hasta):
        return self.filter(inicio__lt=hasta, fin__gt=desde)

    def del_dia(self, fecha):
        return self.entre(*limites_dia(fecha))

    def solapadas(self, inicio, fin, excluir_id=None):
        qs = self.activas().filter(inicio__lt=fin, fin__gt=inicio)
        return qs.exclude(pk=excluir_id) if excluir_id else qs


class Cita(models.Model):
    class CanceladaPor(models.TextChoices):
        ESTUDIO = "estudio", _("El estudio")
        CLIENTE = "cliente", _("El cliente")

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="citas")
    tipo = models.ForeignKey(TipoCita, on_delete=models.PROTECT, related_name="citas")
    tatuaje = models.ForeignKey(Tatuaje, null=True, blank=True, on_delete=models.SET_NULL, related_name="citas")
    inicio = models.DateTimeField(_("Inicio"))
    fin = models.DateTimeField(_("Fin"))
    estado = models.CharField(_("Estado"), max_length=12, choices=EstadoCita.choices, default=EstadoCita.CONFIRMADA)
    descripcion = models.CharField(_("Qué se hace"), max_length=200, blank=True)
    precio = models.DecimalField(_("Precio previsto"), max_digits=10, decimal_places=2, null=True, blank=True)
    notas = models.TextField(_("Notas de preparación"), blank=True)
    notas_sesion = models.TextField(_("Notas de la sesión"), blank=True)
    confirmada_cliente_en = models.DateTimeField(null=True, blank=True)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.CharField(max_length=10, choices=CanceladaPor.choices, blank=True)
    motivo_cancelacion = models.CharField(_("Motivo"), max_length=200, blank=True)
    reprogramacion_pedida = models.CharField(max_length=300, blank=True)
    reprogramacion_pedida_en = models.DateTimeField(null=True, blank=True)
    reprogramacion_atendida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = CitaQuerySet.as_manager()

    class Meta:
        ordering = ["inicio"]
        indexes = [models.Index(fields=["inicio"]), models.Index(fields=["estado", "inicio"])]
        constraints = [
            models.CheckConstraint(condition=Q(fin__gt=F("inicio")), name="cita_fin_posterior_inicio"),
            # Garantía en la propia base de datos: dos citas activas nunca se solapan,
            # aunque dos peticiones lleguen a la vez.
            ExclusionConstraint(
                name="cita_sin_solapes",
                expressions=[(TsTzRange("inicio", "fin", RangeBoundary()), RangeOperators.OVERLAPS)],
                condition=Q(estado__in=ESTADOS_ACTIVOS),
            ),
        ]

    def __str__(self):
        return f"{self.cliente} · {timezone.localtime(self.inicio):%d/%m %H:%M}"

    @property
    def duracion_minutos(self) -> int:
        return int((self.fin - self.inicio).total_seconds() // 60)

    @property
    def activa(self) -> bool:
        return self.estado in ESTADOS_ACTIVOS

    @property
    def pendiente(self) -> bool:
        return self.estado in ESTADOS_PENDIENTES

    @property
    def es_futura(self) -> bool:
        return self.inicio > timezone.now()

    @property
    def puede_gestionarla_cliente(self) -> bool:
        return self.pendiente and self.es_futura

    @property
    def requiere_atencion(self) -> bool:
        return self.estado == EstadoCita.SOLICITADA or (
            bool(self.reprogramacion_pedida) and not self.reprogramacion_atendida
        )

    @property
    def pagado(self):
        from django.db.models import Sum

        total = self.pagos.filter(devuelto=False).aggregate(t=Sum("importe"))["t"]
        return total or 0


class HorarioLaboral(models.Model):
    class Dia(models.IntegerChoices):
        LUNES = 0, _("Lunes")
        MARTES = 1, _("Martes")
        MIERCOLES = 2, _("Miércoles")
        JUEVES = 3, _("Jueves")
        VIERNES = 4, _("Viernes")
        SABADO = 5, _("Sábado")
        DOMINGO = 6, _("Domingo")

    dia_semana = models.PositiveSmallIntegerField(choices=Dia.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        ordering = ["dia_semana", "hora_inicio"]
        constraints = [
            models.CheckConstraint(condition=Q(hora_fin__gt=F("hora_inicio")), name="horario_fin_posterior"),
        ]

    def __str__(self):
        return f"{self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}"


class Bloqueo(models.Model):
    class Tipo(models.TextChoices):
        DIA_LIBRE = "dia_libre", _("Día libre")
        VACACIONES = "vacaciones", _("Vacaciones")
        EVENTO = "evento", _("Convención / evento")
        BLOQUEO = "bloqueo", _("Bloqueo")

    tipo = models.CharField(_("Tipo"), max_length=12, choices=Tipo.choices, default=Tipo.BLOQUEO)
    motivo = models.CharField(_("Motivo"), max_length=120, blank=True)
    inicio = models.DateTimeField(_("Desde"))
    fin = models.DateTimeField(_("Hasta"))
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["inicio"]
        indexes = [models.Index(fields=["inicio", "fin"])]
        constraints = [models.CheckConstraint(condition=Q(fin__gt=F("inicio")), name="bloqueo_fin_posterior")]

    def __str__(self):
        return self.motivo or self.get_tipo_display()


class EntradaListaEspera(models.Model):
    class Franja(models.TextChoices):
        CUALQUIERA = "cualquiera", _("Cualquier hora")
        MANANA = "manana", _("Mañana")
        TARDE = "tarde", _("Tarde")

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="lista_espera")
    tipo = models.ForeignKey(TipoCita, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Tipo de cita"))
    dias = ArrayField(
        models.PositiveSmallIntegerField(), default=list, blank=True, verbose_name=_("Días que le van bien")
    )
    franja = models.CharField(_("Franja"), max_length=12, choices=Franja.choices, default=Franja.CUALQUIERA)
    notas = models.CharField(_("Notas"), max_length=200, blank=True)
    prioritaria = models.BooleanField(_("Prioritaria"), default=False)
    activa = models.BooleanField(default=True)
    ofrecido_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-prioritaria", "creado_en"]
        verbose_name = _("entrada de lista de espera")

    def __str__(self):
        return _("%(cliente)s (espera)") % {"cliente": self.cliente}

    def dias_legibles(self) -> str:
        if not self.dias:
            return _("Cualquier día")
        nombres = dict(HorarioLaboral.Dia.choices)
        return ", ".join(nombres[d][:3].lower() for d in sorted(self.dias))


class SolicitudReserva(models.Model):
    """Lo que llega desde la página pública de reservas."""

    class Estado(models.TextChoices):
        NUEVA = "nueva", _("Nueva")
        APROBADA = "aprobada", _("Aceptada · sin fecha")
        CONVERTIDA = "convertida", _("Con cita")
        RECHAZADA = "rechazada", _("Rechazada")
        SPAM = "spam", _("Spam")

    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.NUEVA)
    nombre = models.CharField(_("Nombre"), max_length=80)
    apellidos = models.CharField(_("Apellidos"), max_length=120, blank=True)
    telefono = models.CharField(_("Teléfono"), max_length=20)
    email = models.EmailField(_("Email"), blank=True)
    instagram = models.CharField(_("Instagram"), max_length=60, blank=True)
    fecha_nacimiento = models.DateField(_("Fecha de nacimiento"))
    descripcion = models.TextField(_("Tu idea"))
    zona = models.CharField(_("Zona del cuerpo"), max_length=20, choices=Tatuaje.Zona.choices, blank=True)
    tamano = models.CharField(_("Tamaño aproximado"), max_length=10, choices=Tatuaje.Tamano.choices, blank=True)
    estilo = models.CharField(_("Estilo"), max_length=20, choices=Tatuaje.Estilo.choices, blank=True)
    medidas = models.CharField(_("Medidas"), max_length=40, blank=True)
    fechas_preferidas = models.CharField(_("Fechas que te vienen bien"), max_length=300, blank=True)
    presupuesto = models.CharField(_("Presupuesto orientativo"), max_length=60, blank=True)
    primer_tatuaje = models.BooleanField(_("Es mi primer tatuaje"), default=False)
    acepta_marketing = models.BooleanField(default=False)
    diseno_flash = models.ForeignKey(
        "catalogo.DisenoFlash", null=True, blank=True, on_delete=models.SET_NULL, related_name="solicitudes"
    )
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.SET_NULL, related_name="solicitudes")
    tatuaje = models.ForeignKey(Tatuaje, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cita = models.ForeignKey(Cita, null=True, blank=True, on_delete=models.SET_NULL, related_name="solicitudes")
    huella_ip = models.CharField(max_length=64, blank=True, help_text=_("Hash de la IP (no se guarda la IP)."))
    motivo_rechazo = models.CharField(max_length=200, blank=True)
    triaje = models.JSONField(null=True, blank=True)
    triaje_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["estado", "-creado_en"])]
        verbose_name = _("solicitud de reserva")
        verbose_name_plural = _("solicitudes de reserva")

    def __str__(self):
        return f"{self.nombre_completo} · {self.creado_en:%d/%m}"

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()

    @property
    def edad(self) -> int:
        hoy = timezone.localdate()
        n = self.fecha_nacimiento
        return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))


class ImagenSolicitud(models.Model):
    solicitud = models.ForeignKey(SolicitudReserva, on_delete=models.CASCADE, related_name="imagenes")
    imagen = models.ImageField(upload_to="privado/solicitudes/%Y/%m/")
    miniatura = models.ImageField(upload_to="privado/solicitudes/%Y/%m/")
    creado_en = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return _("Imagen de %(solicitud)s") % {"solicitud": self.solicitud}
