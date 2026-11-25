import calendar as cal
from datetime import date, timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Categoria(models.TextChoices):
    RECORDATORIO = "recordatorio", _("Recordatorio de cita")
    CUIDADO = "cuidado", _("Cuidados posteriores")
    RETOQUE = "retoque", _("Oferta de retoque")
    LISTA_ESPERA = "lista_espera", _("Hueco libre")
    SOLICITUD = "solicitud", _("Respuesta a solicitud")
    CUMPLEANOS = "cumpleanos", _("Cumpleaños")
    ANIVERSARIO = "aniversario", _("Aniversario del tatuaje")
    FECHA_DESTACADA = "fecha_destacada", _("Fecha destacada")
    CAMPANA = "campana", _("Campaña")
    REACTIVACION = "reactivacion", _("Reactivación")
    GENERAL = "general", _("Mensaje libre")


# Orden de la bandeja: primero lo que caduca antes o es de servicio.
PRIORIDAD = {c: i for i, c in enumerate(Categoria.values)}
ICONOS = {
    Categoria.RECORDATORIO: "reloj",
    Categoria.CUIDADO: "gota",
    Categoria.RETOQUE: "aguja",
    Categoria.LISTA_ESPERA: "agenda",
    Categoria.SOLICITUD: "bandeja",
    Categoria.CUMPLEANOS: "regalo",
    Categoria.ANIVERSARIO: "corazon",
    Categoria.FECHA_DESTACADA: "estrella",
    Categoria.CAMPANA: "enviar",
    Categoria.REACTIVACION: "refrescar",
    Categoria.GENERAL: "mensajes",
}
PROMOCIONALES = {
    Categoria.CUMPLEANOS,
    Categoria.ANIVERSARIO,
    Categoria.FECHA_DESTACADA,
    Categoria.CAMPANA,
    Categoria.REACTIVACION,
}


class Canal(models.TextChoices):
    WHATSAPP = "whatsapp_link", _("WhatsApp")
    SMS = "sms_link", _("SMS / RCS")
    COPIA = "copia", _("Copiado")
    WHATSAPP_API = "whatsapp_api", _("WhatsApp (API oficial)")


class Plantilla(models.Model):
    nombre = models.CharField(_("Nombre"), max_length=80)
    categoria = models.CharField(_("Para"), max_length=20, choices=Categoria.choices, default=Categoria.GENERAL)
    cuerpo = models.TextField(_("Texto"))
    es_promocional = models.BooleanField(
        _("Es promocional"),
        default=False,
        help_text=_("Solo se preparará para clientes que aceptaron recibir promociones."),
    )
    predeterminada = models.BooleanField(
        _("Usar por defecto"), default=False, help_text=_("La que se usa automáticamente para esta categoría.")
    )
    activa = models.BooleanField(_("Activa"), default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["categoria", "-predeterminada", "nombre"]

    def __str__(self):
        return self.nombre

    @classmethod
    def para(cls, categoria: str) -> "Plantilla | None":
        return cls.objects.filter(categoria=categoria, activa=True).order_by("-predeterminada", "pk").first()


class PasoCuidado(models.Model):
    nombre = models.CharField(_("Nombre"), max_length=60, help_text=_("Ej.: Día 3"))
    dias_despues = models.PositiveSmallIntegerField(_("Días tras la sesión"))
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, related_name="pasos_cuidado")
    es_oferta_retoque = models.BooleanField(
        _("Ofrece el retoque"),
        default=False,
        help_text=_("No se envía si ya hubo retoque o quedan sesiones pendientes."),
    )
    activo = models.BooleanField(_("Activo"), default=True)

    class Meta:
        ordering = ["dias_despues"]
        verbose_name = _("paso de cuidados")

    def __str__(self):
        return f"{self.nombre} (+{self.dias_despues} d)"


class FechaDestacada(models.Model):
    class Regla(models.TextChoices):
        FIJA = "fija", _("Mismo día cada año")
        NTH = "nth", _("N-ésimo día de la semana del mes")
        ULTIMO = "ultimo", _("Último día de la semana del mes")
        VIERNES13 = "viernes13", _("Cada viernes 13")
        UNICA = "unica", _("Una fecha concreta")

    class DiaSemana(models.IntegerChoices):
        LUNES = 0, _("lunes")
        MARTES = 1, _("martes")
        MIERCOLES = 2, _("miércoles")
        JUEVES = 3, _("jueves")
        VIERNES = 4, _("viernes")
        SABADO = 5, _("sábado")
        DOMINGO = 6, _("domingo")

    nombre = models.CharField(_("Nombre"), max_length=80)
    regla = models.CharField(_("Se repite"), max_length=10, choices=Regla.choices, default=Regla.FIJA)
    mes = models.PositiveSmallIntegerField(_("Mes"), null=True, blank=True)
    dia = models.PositiveSmallIntegerField(_("Día"), null=True, blank=True)
    semana = models.PositiveSmallIntegerField(_("Semana del mes"), null=True, blank=True, help_text=_("1 = primera"))
    dia_semana = models.PositiveSmallIntegerField(
        _("Día de la semana"), choices=DiaSemana.choices, null=True, blank=True
    )
    fecha = models.DateField(_("Fecha"), null=True, blank=True)
    plantilla = models.ForeignKey(
        Plantilla, null=True, blank=True, on_delete=models.SET_NULL, related_name="fechas_destacadas"
    )
    dias_ventana = models.PositiveSmallIntegerField(
        _("Repartir en (días)"), default=1, help_text=_("Los mensajes se reparten en estos días, terminando ese día.")
    )
    segmento = models.CharField(_("Para"), max_length=20, default="marketing")
    generar_campana = models.BooleanField(_("Preparar mensajes"), default=True)
    activa = models.BooleanField(_("Activa"), default=True)

    class Meta:
        ordering = ["mes", "dia", "nombre"]
        verbose_name = _("fecha destacada")
        verbose_name_plural = _("fechas destacadas")

    def __str__(self):
        return self.nombre

    def fecha_en(self, anio: int) -> date | None:
        try:
            if self.regla == self.Regla.FIJA and self.mes and self.dia:
                return date(anio, self.mes, min(self.dia, cal.monthrange(anio, self.mes)[1]))
            if self.regla == self.Regla.NTH and self.mes and self.semana and self.dia_semana is not None:
                primero = date(anio, self.mes, 1)
                desfase = (self.dia_semana - primero.weekday()) % 7
                d = primero + timedelta(days=desfase + 7 * (self.semana - 1))
                return d if d.month == self.mes else None
            if self.regla == self.Regla.ULTIMO and self.mes and self.dia_semana is not None:
                ultimo = date(anio, self.mes, cal.monthrange(anio, self.mes)[1])
                return ultimo - timedelta(days=(ultimo.weekday() - self.dia_semana) % 7)
            if self.regla == self.Regla.UNICA and self.fecha:
                return self.fecha if self.fecha.year == anio else None
        except ValueError:
            return None
        return None

    def proxima(self, desde: date) -> date | None:
        if self.regla == self.Regla.VIERNES13:
            d = date(desde.year, desde.month, 13)
            if d < desde:
                d = date(desde.year + (desde.month == 12), desde.month % 12 + 1, 13)
            while d.weekday() != 4:
                d = date(d.year + (d.month == 12), d.month % 12 + 1, 13)
            return d
        for anio in (desde.year, desde.year + 1):
            d = self.fecha_en(anio)
            if d and d >= desde:
                return d
        return None

    def descripcion_regla(self) -> str:
        from django.utils.dates import MONTHS
        from django.utils.formats import date_format

        ordinales = {1: _("1.er"), 2: _("2.º"), 3: _("3.er"), 4: _("4.º"), 5: _("5.º")}
        if self.regla == self.Regla.FIJA and self.mes:
            return _("Cada %(dia)s de %(mes)s") % {"dia": self.dia, "mes": MONTHS[self.mes]}
        if self.regla == self.Regla.NTH and self.mes:
            return _("%(ordinal)s %(dia)s de %(mes)s") % {
                "ordinal": ordinales.get(self.semana, ""),
                "dia": self.get_dia_semana_display(),
                "mes": MONTHS[self.mes],
            }
        if self.regla == self.Regla.ULTIMO and self.mes:
            return _("Último %(dia)s de %(mes)s") % {"dia": self.get_dia_semana_display(), "mes": MONTHS[self.mes]}
        if self.regla == self.Regla.UNICA and self.fecha:
            return date_format(self.fecha, "SHORT_DATE_FORMAT")
        return self.get_regla_display()


class Campana(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", _("Borrador")
        ACTIVA = "activa", _("En curso")
        COMPLETADA = "completada", _("Completada")
        CANCELADA = "cancelada", _("Cancelada")

    nombre = models.CharField(_("Nombre"), max_length=100)
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, related_name="campanas")
    segmento = models.CharField(_("Segmento"), max_length=20)
    fecha_inicio = models.DateField(_("Empezar el"), default=timezone.localdate)
    fecha_limite = models.DateField(null=True, blank=True)
    por_dia = models.PositiveSmallIntegerField(_("Mensajes por día"), default=10)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    fecha_destacada = models.ForeignKey(
        FechaDestacada, null=True, blank=True, on_delete=models.SET_NULL, related_name="campanas"
    )
    anio = models.PositiveIntegerField(null=True, blank=True)  # año (o AAAAMM para los viernes 13)
    total = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["fecha_destacada", "anio"],
                condition=Q(fecha_destacada__isnull=False),
                name="campana_unica_por_fecha_y_anio",
            )
        ]

    def __str__(self):
        return self.nombre


class MensajeQuerySet(models.QuerySet):
    def pendientes(self):
        return self.filter(estado=MensajePreparado.Estado.PENDIENTE)

    def para_hoy(self, hoy: date | None = None):
        hoy = hoy or timezone.localdate()
        return (
            self.pendientes()
            .filter(fecha_programada__lte=hoy)
            .filter(Q(caduca_el__isnull=True) | Q(caduca_el__gte=hoy))
            .filter(cliente__anonimizado_en__isnull=True, cliente__contacto_bloqueado=False)
            # El consentimiento se comprueba también al mostrar: si alguien se dio
            # de baja después de preparar el mensaje, ya no aparece.
            .exclude(es_promocional=True, cliente__marketing_consentimiento=False)
        )


class MensajePreparado(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", _("Pendiente")
        ENVIADO = "enviado", _("Enviado")
        DESCARTADO = "descartado", _("Descartado")
        CADUCADO = "caducado", _("Caducado")

    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.CASCADE, related_name="mensajes")
    tipo = models.CharField(max_length=20, choices=Categoria.choices)
    # Identifica el motivo del mensaje (p. ej. «cuidado:812:3»). Al ser única,
    # repetir la generación nunca duplica mensajes.
    clave = models.CharField(max_length=160, unique=True)
    texto = models.TextField()
    motivo = models.CharField(max_length=200, blank=True)
    plantilla = models.ForeignKey(Plantilla, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    es_promocional = models.BooleanField(default=False)
    fecha_programada = models.DateField(default=timezone.localdate)
    caduca_el = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    pospuesto_veces = models.PositiveSmallIntegerField(default=0)
    canal_usado = models.CharField(max_length=16, choices=Canal.choices, blank=True)
    abierto_en = models.DateTimeField(null=True, blank=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    descartado_en = models.DateTimeField(null=True, blank=True)
    motivo_descarte = models.CharField(max_length=120, blank=True)
    cita = models.ForeignKey("agenda.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="mensajes")
    tatuaje = models.ForeignKey(
        "clientes.Tatuaje", null=True, blank=True, on_delete=models.SET_NULL, related_name="mensajes"
    )
    campana = models.ForeignKey(Campana, null=True, blank=True, on_delete=models.SET_NULL, related_name="mensajes")
    creado_en = models.DateTimeField(default=timezone.now)

    objects = MensajeQuerySet.as_manager()

    class Meta:
        ordering = ["fecha_programada", "pk"]
        indexes = [
            models.Index(fields=["estado", "fecha_programada"]),
            models.Index(fields=["cliente", "estado"]),
            models.Index(fields=["enviado_en"]),
        ]
        verbose_name = _("mensaje preparado")
        verbose_name_plural = _("mensajes preparados")

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.cliente}"

    @property
    def icono(self) -> str:
        return ICONOS.get(self.tipo, "mensajes")

    @property
    def prioridad(self) -> int:
        return PRIORIDAD.get(self.tipo, 99)
