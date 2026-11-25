import calendar as cal
from datetime import date, timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Categoria(models.TextChoices):
    RECORDATORIO = "recordatorio", "Recordatorio de cita"
    CUIDADO = "cuidado", "Cuidados posteriores"
    RETOQUE = "retoque", "Oferta de retoque"
    LISTA_ESPERA = "lista_espera", "Hueco libre"
    SOLICITUD = "solicitud", "Respuesta a solicitud"
    CUMPLEANOS = "cumpleanos", "Cumpleaños"
    ANIVERSARIO = "aniversario", "Aniversario del tatuaje"
    FECHA_DESTACADA = "fecha_destacada", "Fecha destacada"
    CAMPANA = "campana", "Campaña"
    REACTIVACION = "reactivacion", "Reactivación"
    GENERAL = "general", "Mensaje libre"


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
    WHATSAPP = "whatsapp_link", "WhatsApp"
    SMS = "sms_link", "SMS / RCS"
    COPIA = "copia", "Copiado"
    WHATSAPP_API = "whatsapp_api", "WhatsApp (API oficial)"


class Plantilla(models.Model):
    nombre = models.CharField("Nombre", max_length=80)
    categoria = models.CharField("Para", max_length=20, choices=Categoria.choices, default=Categoria.GENERAL)
    cuerpo = models.TextField("Texto")
    es_promocional = models.BooleanField(
        "Es promocional",
        default=False,
        help_text="Solo se preparará para clientes que aceptaron recibir promociones.",
    )
    predeterminada = models.BooleanField(
        "Usar por defecto", default=False, help_text="La que se usa automáticamente para esta categoría."
    )
    activa = models.BooleanField("Activa", default=True)
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
    nombre = models.CharField("Nombre", max_length=60, help_text="Ej.: Día 3")
    dias_despues = models.PositiveSmallIntegerField("Días tras la sesión")
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, related_name="pasos_cuidado")
    es_oferta_retoque = models.BooleanField(
        "Ofrece el retoque", default=False, help_text="No se envía si ya hubo retoque o quedan sesiones pendientes."
    )
    activo = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["dias_despues"]
        verbose_name = "paso de cuidados"

    def __str__(self):
        return f"{self.nombre} (+{self.dias_despues} d)"


class FechaDestacada(models.Model):
    class Regla(models.TextChoices):
        FIJA = "fija", "Mismo día cada año"
        NTH = "nth", "N-ésimo día de la semana del mes"
        ULTIMO = "ultimo", "Último día de la semana del mes"
        VIERNES13 = "viernes13", "Cada viernes 13"
        UNICA = "unica", "Una fecha concreta"

    class DiaSemana(models.IntegerChoices):
        LUNES = 0, "lunes"
        MARTES = 1, "martes"
        MIERCOLES = 2, "miércoles"
        JUEVES = 3, "jueves"
        VIERNES = 4, "viernes"
        SABADO = 5, "sábado"
        DOMINGO = 6, "domingo"

    nombre = models.CharField("Nombre", max_length=80)
    regla = models.CharField("Se repite", max_length=10, choices=Regla.choices, default=Regla.FIJA)
    mes = models.PositiveSmallIntegerField("Mes", null=True, blank=True)
    dia = models.PositiveSmallIntegerField("Día", null=True, blank=True)
    semana = models.PositiveSmallIntegerField("Semana del mes", null=True, blank=True, help_text="1 = primera")
    dia_semana = models.PositiveSmallIntegerField("Día de la semana", choices=DiaSemana.choices, null=True, blank=True)
    fecha = models.DateField("Fecha", null=True, blank=True)
    plantilla = models.ForeignKey(
        Plantilla, null=True, blank=True, on_delete=models.SET_NULL, related_name="fechas_destacadas"
    )
    dias_ventana = models.PositiveSmallIntegerField(
        "Repartir en (días)", default=1, help_text="Los mensajes se reparten en estos días, terminando ese día."
    )
    segmento = models.CharField("Para", max_length=20, default="marketing")
    generar_campana = models.BooleanField("Preparar mensajes", default=True)
    activa = models.BooleanField("Activa", default=True)

    class Meta:
        ordering = ["mes", "dia", "nombre"]
        verbose_name = "fecha destacada"
        verbose_name_plural = "fechas destacadas"

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
        meses = [
            "",
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]
        ordinales = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º", 5: "5.º"}
        if self.regla == self.Regla.FIJA and self.mes:
            return f"Cada {self.dia} de {meses[self.mes]}"
        if self.regla == self.Regla.NTH and self.mes:
            return f"{ordinales.get(self.semana, '')} {self.get_dia_semana_display()} de {meses[self.mes]}"
        if self.regla == self.Regla.ULTIMO and self.mes:
            return f"Último {self.get_dia_semana_display()} de {meses[self.mes]}"
        if self.regla == self.Regla.UNICA and self.fecha:
            return self.fecha.strftime("%d/%m/%Y")
        return self.get_regla_display()


class Campana(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ACTIVA = "activa", "En curso"
        COMPLETADA = "completada", "Completada"
        CANCELADA = "cancelada", "Cancelada"

    nombre = models.CharField("Nombre", max_length=100)
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, related_name="campanas")
    segmento = models.CharField("Segmento", max_length=20)
    fecha_inicio = models.DateField("Empezar el", default=timezone.localdate)
    fecha_limite = models.DateField(null=True, blank=True)
    por_dia = models.PositiveSmallIntegerField("Mensajes por día", default=10)
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
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        DESCARTADO = "descartado", "Descartado"
        CADUCADO = "caducado", "Caducado"

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
        verbose_name = "mensaje preparado"
        verbose_name_plural = "mensajes preparados"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.cliente}"

    @property
    def icono(self) -> str:
        return ICONOS.get(self.tipo, "mensajes")

    @property
    def prioridad(self) -> int:
        return PRIORIDAD.get(self.tipo, 99)
