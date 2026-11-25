from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.nucleo.archivos import ruta_tatuajes


class Etiqueta(models.Model):
    nombre = models.CharField("Nombre", max_length=40)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [models.UniqueConstraint(Lower("nombre"), name="etiqueta_nombre_unico_ci")]

    def __str__(self):
        return self.nombre


class OrigenConsentimiento(models.TextChoices):
    FORMULARIO = "formulario", "Formulario de reserva"
    PRESENCIAL = "presencial", "En persona"
    VERBAL = "verbal", "De palabra / llamada"
    MENSAJE = "mensaje", "Por mensaje"
    PETICION_BAJA = "peticion_baja", "Pidió la baja"


class ClienteQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(anonimizado_en__isnull=True)

    def contactables(self):
        return self.activos().filter(contacto_bloqueado=False)

    def con_marketing(self):
        return self.contactables().filter(marketing_consentimiento=True)

    def buscar(self, texto: str):
        texto = (texto or "").strip()
        if not texto:
            return self
        digitos = "".join(c for c in texto if c.isdigit())
        filtro = Q()
        for palabra in texto.split():
            filtro &= (
                Q(nombre__unaccent__icontains=palabra)
                | Q(apellidos__unaccent__icontains=palabra)
                | Q(email__icontains=palabra)
                | Q(instagram__icontains=palabra.lstrip("@"))
            )
        if len(digitos) >= 3:
            filtro |= Q(telefono__contains=digitos)
        return self.filter(filtro)


class Cliente(models.Model):
    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS / RCS"

    class Origen(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        RECOMENDACION = "recomendacion", "Recomendación"
        WEB = "web", "Formulario web"
        ESTUDIO = "estudio", "Pasó por el estudio"
        EVENTO = "evento", "Convención / evento"
        OTRO = "otro", "Otro"

    nombre = models.CharField("Nombre", max_length=80)
    apellidos = models.CharField("Apellidos", max_length=120, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True, help_text="Con prefijo si no es de EE. UU.")
    email = models.EmailField("Email", blank=True)
    instagram = models.CharField("Instagram", max_length=60, blank=True)
    fecha_nacimiento = models.DateField("Fecha de nacimiento", null=True, blank=True)
    canal_preferido = models.CharField("Canal preferido", max_length=10, choices=Canal.choices, default=Canal.WHATSAPP)
    contacto_bloqueado = models.BooleanField(
        "No contactar", default=False, help_text="No se le preparará ningún mensaje, ni siquiera recordatorios."
    )
    marketing_consentimiento = models.BooleanField("Acepta mensajes promocionales", default=False)
    marketing_fecha = models.DateTimeField(null=True, blank=True)
    marketing_origen = models.CharField(max_length=20, choices=OrigenConsentimiento.choices, blank=True)
    origen = models.CharField("Cómo llegó", max_length=20, choices=Origen.choices, blank=True)
    notas = models.TextField("Notas privadas", blank=True)
    etiquetas = models.ManyToManyField(Etiqueta, blank=True, related_name="clientes")
    anonimizado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        ordering = ["nombre", "apellidos"]
        indexes = [
            models.Index(fields=["apellidos", "nombre"]),
            models.Index(fields=["telefono"]),
            models.Index(fields=["creado_en"]),
        ]

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()

    @property
    def edad(self) -> int | None:
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        n = self.fecha_nacimiento
        return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))

    def es_menor(self, edad_minima: int | None = None) -> bool:
        if self.edad is None:
            return False
        if edad_minima is None:
            from apps.nucleo.models import AjustesEstudio

            edad_minima = AjustesEstudio.obtener().edad_minima
        return self.edad < edad_minima

    @property
    def anonimizado(self) -> bool:
        return self.anonimizado_en is not None

    @property
    def puede_recibir_promociones(self) -> bool:
        return self.marketing_consentimiento and not self.contacto_bloqueado and not self.anonimizado

    @property
    def es_vip(self) -> bool:
        return any(e.nombre.lower() == "vip" for e in self.etiquetas.all())

    def cumple_en(self, anio: int) -> date | None:
        if not self.fecha_nacimiento:
            return None
        n = self.fecha_nacimiento
        try:
            return n.replace(year=anio)
        except ValueError:  # 29 de febrero en año no bisiesto
            return date(anio, 2, 28)

    def dar_consentimiento(self, origen: str, usuario=None, notas: str = "") -> None:
        self.marketing_consentimiento = True
        self.marketing_fecha = timezone.now()
        self.marketing_origen = origen
        self.save(update_fields=["marketing_consentimiento", "marketing_fecha", "marketing_origen", "actualizado_en"])
        EventoConsentimiento.objects.create(
            cliente=self, tipo=EventoConsentimiento.Tipo.ALTA, origen=origen, usuario=usuario, notas=notas
        )

    def retirar_consentimiento(self, origen: str, usuario=None, notas: str = "") -> None:
        self.marketing_consentimiento = False
        self.marketing_fecha = timezone.now()
        self.marketing_origen = origen
        self.save(update_fields=["marketing_consentimiento", "marketing_fecha", "marketing_origen", "actualizado_en"])
        EventoConsentimiento.objects.create(
            cliente=self, tipo=EventoConsentimiento.Tipo.BAJA, origen=origen, usuario=usuario, notas=notas
        )


class EventoConsentimiento(models.Model):
    """Historial inmutable de altas y bajas del consentimiento de marketing."""

    class Tipo(models.TextChoices):
        ALTA = "alta", "Alta"
        BAJA = "baja", "Baja"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="eventos_consentimiento")
    tipo = models.CharField(max_length=4, choices=Tipo.choices)
    origen = models.CharField(max_length=20, choices=OrigenConsentimiento.choices)
    notas = models.CharField(max_length=200, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.get_origen_display()}"


class DatosSalud(models.Model):
    """Datos de salud. Tabla separada a propósito: nunca se envían a la IA."""

    cliente = models.OneToOneField(Cliente, on_delete=models.CASCADE, related_name="salud")
    alergias = models.TextField("Alergias", blank=True, help_text="Látex, pigmentos, antibióticos, cremas…")
    medicacion = models.TextField("Medicación actual", blank=True)
    anticoagulantes = models.BooleanField("Toma anticoagulantes", default=False)
    diabetes = models.BooleanField("Diabetes", default=False)
    epilepsia = models.BooleanField("Epilepsia", default=False)
    problemas_cardiacos = models.BooleanField("Problemas cardíacos", default=False)
    embarazo_lactancia = models.BooleanField("Embarazo o lactancia", default=False)
    condiciones_piel = models.TextField(
        "Condiciones de la piel", blank=True, help_text="Psoriasis, queloides, dermatitis…"
    )
    otras = models.TextField("Otras observaciones", blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "datos de salud"

    def __str__(self):
        return f"Salud de {self.cliente}"

    def alertas(self) -> list[str]:
        lista = []
        if self.alergias.strip():
            lista.append("Alergias")
        if self.anticoagulantes:
            lista.append("Anticoagulantes")
        if self.diabetes:
            lista.append("Diabetes")
        if self.epilepsia:
            lista.append("Epilepsia")
        if self.problemas_cardiacos:
            lista.append("Cardíaco")
        if self.embarazo_lactancia:
            lista.append("Embarazo/lactancia")
        if self.condiciones_piel.strip():
            lista.append("Piel")
        return lista


class Tatuaje(models.Model):
    class Estado(models.TextChoices):
        EN_PROCESO = "en_proceso", "En proceso"
        TERMINADO = "terminado", "Terminado"

    class Zona(models.TextChoices):
        BRAZO = "brazo", "Brazo"
        ANTEBRAZO = "antebrazo", "Antebrazo"
        MANO = "mano", "Mano / dedos"
        HOMBRO = "hombro", "Hombro"
        ESPALDA = "espalda", "Espalda"
        PECHO = "pecho", "Pecho"
        COSTILLAS = "costillas", "Costillas"
        ABDOMEN = "abdomen", "Abdomen"
        CADERA = "cadera", "Cadera"
        MUSLO = "muslo", "Muslo"
        PIERNA = "pierna", "Pierna / gemelo"
        TOBILLO = "tobillo", "Tobillo / pie"
        CUELLO = "cuello", "Cuello / nuca"
        CARA = "cara", "Cara / cabeza"
        OREJA = "oreja", "Oreja"
        OTRA = "otra", "Otra"

    class Estilo(models.TextChoices):
        FINE_LINE = "fine_line", "Fine line"
        BLACKWORK = "blackwork", "Blackwork"
        REALISMO = "realismo", "Realismo"
        TRADICIONAL = "tradicional", "Tradicional"
        NEOTRADICIONAL = "neotradicional", "Neotradicional"
        ACUARELA = "acuarela", "Acuarela"
        GEOMETRICO = "geometrico", "Geométrico"
        LETTERING = "lettering", "Lettering"
        MINIMALISTA = "minimalista", "Minimalista"
        JAPONES = "japones", "Japonés"
        DOTWORK = "dotwork", "Dotwork"
        OTRO = "otro", "Otro"

    class Tamano(models.TextChoices):
        MINI = "mini", "Mini (< 5 cm)"
        PEQUENO = "pequeno", "Pequeño (5-10 cm)"
        MEDIANO = "mediano", "Mediano (10-20 cm)"
        GRANDE = "grande", "Grande (20-30 cm)"
        XL = "xl", "Muy grande (> 30 cm)"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="tatuajes")
    titulo = models.CharField("Título", max_length=120)
    zona = models.CharField("Zona", max_length=20, choices=Zona.choices, blank=True)
    estilo = models.CharField("Estilo", max_length=20, choices=Estilo.choices, blank=True)
    tamano = models.CharField("Tamaño", max_length=10, choices=Tamano.choices, blank=True)
    medidas = models.CharField("Medidas", max_length=40, blank=True, help_text="Ej.: 12 × 8 cm")
    estado = models.CharField("Estado", max_length=12, choices=Estado.choices, default=Estado.EN_PROCESO)
    fecha_inicio = models.DateField("Primera sesión", null=True, blank=True)
    fecha_fin = models.DateField("Terminado el", null=True, blank=True)
    sesiones_previstas = models.PositiveSmallIntegerField("Sesiones previstas", null=True, blank=True)
    precio_total = models.DecimalField("Precio acordado", max_digits=10, decimal_places=2, null=True, blank=True)
    retoque_hecho = models.BooleanField("Retoque hecho", default=False)
    notas = models.TextField("Notas", blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha_inicio", "-creado_en"]
        indexes = [models.Index(fields=["estado"]), models.Index(fields=["fecha_fin"])]

    def __str__(self):
        return self.titulo

    @property
    def fecha_aniversario(self) -> date | None:
        return self.fecha_fin or self.fecha_inicio

    @property
    def sesiones_realizadas(self) -> int:
        return self.citas.filter(estado="realizada").count()

    def portada(self):
        fotos = list(self.fotos.all())
        for tipo in (FotoTatuaje.Tipo.CICATRIZADO, FotoTatuaje.Tipo.RESULTADO, FotoTatuaje.Tipo.REFERENCIA):
            for f in fotos:
                if f.tipo == tipo:
                    return f
        return None


class FotoTatuaje(models.Model):
    class Tipo(models.TextChoices):
        REFERENCIA = "referencia", "Referencia"
        RESULTADO = "resultado", "Recién hecho"
        CICATRIZADO = "cicatrizado", "Cicatrizado"

    tatuaje = models.ForeignKey(Tatuaje, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.RESULTADO)
    imagen = models.ImageField(upload_to=ruta_tatuajes)
    miniatura = models.ImageField(upload_to=ruta_tatuajes)
    nota = models.CharField(max_length=160, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["tipo", "-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.tatuaje}"


class NotaCliente(models.Model):
    class Origen(models.TextChoices):
        MANUAL = "manual", "Nota"
        DICTADO = "dictado", "Dictado"
        SESION = "sesion", "Tras la sesión"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="notas_cliente")
    cita = models.ForeignKey(
        "agenda.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="notas_cliente"
    )
    texto = models.TextField("Nota")
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.MANUAL)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return self.texto[:60]


class ConsentimientoInformado(models.Model):
    """Consentimiento firmado. Inmutable: guarda el texto exacto que se firmó."""

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="consentimientos")
    cita = models.ForeignKey(
        "agenda.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="consentimientos"
    )
    version_texto = models.PositiveIntegerField()
    texto = models.TextField()
    respuestas = models.JSONField(default=dict, help_text="Salud y autorizaciones declaradas al firmar.")
    nombre_firmante = models.CharField(max_length=200)
    firma = models.ImageField(upload_to="privado/consentimientos/%Y/%m/")
    pdf = models.FileField(upload_to="privado/consentimientos/%Y/%m/")
    hash_pdf = models.CharField(max_length=64)
    ip = models.GenericIPAddressField(null=True, blank=True)
    firmado_en = models.DateTimeField(default=timezone.now)
    conservar_hasta = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-firmado_en"]
        verbose_name = "consentimiento informado"
        verbose_name_plural = "consentimientos informados"

    def __str__(self):
        return f"Consentimiento de {self.nombre_firmante} ({self.firmado_en:%d/%m/%Y})"
