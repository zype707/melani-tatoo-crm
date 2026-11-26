"""Datos de demostración: un estudio ficticio con vida (clientes, agenda, mensajes…).

Todos los datos son inventados. Los teléfonos usan el rango 555-01XX,
reservado para ficción en EE. UU.
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.agenda.models import (
    Bloqueo,
    Cita,
    EntradaListaEspera,
    EstadoCita,
    HorarioLaboral,
    ImagenSolicitud,
    SolicitudReserva,
    TipoCita,
)
from apps.catalogo.models import DisenoFlash
from apps.clientes.models import Cliente, DatosSalud, Etiqueta, FotoTatuaje, NotaCliente, Tatuaje
from apps.finanzas.models import Gasto, Pago
from apps.mensajeria.generadores import ejecutar_diario
from apps.mensajeria.models import Categoria, MensajePreparado, Plantilla
from apps.mensajeria.predeterminados import crear_predeterminados
from apps.nucleo import tokens
from apps.nucleo.imagenes import procesar_imagen
from apps.nucleo.models import AjustesEstudio

NOMBRES = [
    ("Lucía", "Méndez"),
    ("Marcus", "Reed"),
    ("Daniela", "Ortiz"),
    ("Elena", "Vargas"),
    ("Jordan", "Price"),
    ("Camila", "Rojas"),
    ("Ashley", "Brooks"),
    ("Valentina", "Cruz"),
    ("Tyler", "Nguyen"),
    ("Sofía", "Herrera"),
    ("Brianna", "Coleman"),
    ("Mateo", "Salazar"),
    ("Isabella", "Ramos"),
    ("Kevin", "Duarte"),
    ("Gabriela", "Lima"),
    ("Destiny", "Morales"),
    ("Andrés", "Peña"),
    ("Mia", "Torres"),
    ("Chris", "Delgado"),
    ("Natalia", "Rivas"),
    ("Jasmine", "Ford"),
    ("Diego", "Castillo"),
    ("Paola", "Benítez"),
    ("Ryan", "Carter"),
    ("Valeria", "Soto"),
    ("Hannah", "Kim"),
    ("Samuel", "Acosta"),
    ("Mariana", "Fuentes"),
    ("Olivia", "Grant"),
    ("Luis", "Navarro"),
    ("Alexa", "Montes"),
    ("Ethan", "Ruiz"),
    ("Carolina", "Vega"),
    ("Taylor", "Bennett"),
    ("Renata", "Molina"),
    ("Javier", "Campos"),
    ("Emily", "Santos"),
    ("Ximena", "Paredes"),
    ("Noah", "Ellis"),
    ("Fernanda", "Aguilar"),
]
TITULOS = {
    "fine_line": ["Rama de olivo", "Luna creciente", "Constelación", "Flor de loto", "Golondrina mínima"],
    "blackwork": ["Serpiente", "Mandala", "Polilla", "Daga ornamental", "Manga botánica"],
    "tradicional": ["Golondrina tradicional", "Pantera", "Corazón con dagas", "Barco"],
    "realismo": ["Retrato de mascota", "León", "Ojo realista"],
    "lettering": ["Frase en el antebrazo", "Fecha especial", "Nombre de su hija"],
    "acuarela": ["Colibrí acuarela", "Peonías"],
    "geometrico": ["Cubo geométrico", "Ciervo geométrico"],
    "minimalista": ["Ola", "Montañas", "Corazón de línea"],
}
ZONAS = ["antebrazo", "brazo", "hombro", "costillas", "muslo", "pierna", "tobillo", "espalda", "mano", "cuello"]
TAMANOS = ["mini", "pequeno", "mediano", "grande", "xl"]
TINTA = (1, 22, 27)
HUESO = (244, 241, 232)


def arte(semilla: int, fondo=HUESO, trazo=TINTA) -> SimpleUploadedFile:
    """Ilustración abstracta generada (no son fotos reales)."""
    r = random.Random(semilla)
    img = Image.new("RGB", (900, 900), fondo)
    d = ImageDraw.Draw(img)
    for _ in range(r.randint(3, 6)):
        x, y, s = r.randint(200, 700), r.randint(200, 700), r.randint(60, 220)
        d.ellipse([x - s, y - s, x + s, y + s], outline=trazo, width=r.randint(6, 14))
    puntos = [(r.randint(150, 750), r.randint(150, 750)) for _ in range(r.randint(3, 6))]
    d.line([*puntos, puntos[0]], fill=trazo, width=10, joint="curve")
    for _ in range(r.randint(20, 60)):
        x, y = r.randint(100, 800), r.randint(100, 800)
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=trazo)
    buf = BytesIO()
    img.save(buf, "PNG")
    return SimpleUploadedFile(f"arte-{semilla}.png", buf.getvalue(), content_type="image/png")


def firma_png() -> str:
    import base64

    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line(
        [(40, 140), (120, 60), (170, 150), (240, 70), (300, 140), (380, 90), (460, 130), (560, 80)],
        fill=(*TINTA, 255),
        width=5,
    )
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class Command(BaseCommand):
    help = "Crea datos de demostración (estudio ficticio en Orlando). No usar con datos reales."

    def add_arguments(self, parser):
        parser.add_argument("--limpiar", action="store_true", help="Borra antes TODOS los datos de negocio.")
        parser.add_argument("--forzar", action="store_true", help="Permite ejecutarlo con DEBUG=False.")
        parser.add_argument("--semilla", type=int, default=2026)

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["forzar"]:
            raise CommandError(
                "Esto crea datos ficticios. Con DEBUG=False añade --forzar si de verdad quieres hacerlo."
            )
        self.r = random.Random(opts["semilla"])
        if opts["limpiar"]:
            self._limpiar()
        elif Cliente.objects.exists():
            raise CommandError("Ya hay clientes. Usa --limpiar para empezar de cero.")
        with transaction.atomic():
            self._estudio()
            clientes = self._clientes()
            self._agenda(clientes)
            self._finanzas()
            self._flash()
            self._solicitudes()
            self._historial_mensajes(clientes)
        self._consentimientos(clientes[:2])
        resultado = ejecutar_diario()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo lista: {Cliente.objects.count()} clientes, {Cita.objects.count()} citas, "
                f"{Tatuaje.objects.count()} tatuajes, {MensajePreparado.objects.pendientes().count()} mensajes en la bandeja."
            )
        )
        self.stdout.write(f"Bandeja de hoy: {resultado}")
        enlace = tokens.enlace_estudio_vigente("reserva")
        self.stdout.write(f"Página de reservas: {settings.SITE_URL}/r/{enlace.token_visible}/")

    # ------------------------------------------------------------------------------------

    def _limpiar(self):
        from apps.nucleo.archivos import borrar_archivo

        for f in list(FotoTatuaje.objects.all()) + list(ImagenSolicitud.objects.all()):
            borrar_archivo(f.imagen)
            borrar_archivo(f.miniatura)
        for d in DisenoFlash.objects.all():
            borrar_archivo(d.imagen)
            borrar_archivo(d.miniatura)
        for modelo in (
            MensajePreparado,
            Pago,
            Gasto,
            SolicitudReserva,
            Cita,
            Bloqueo,
            EntradaListaEspera,
            Cliente,
            Etiqueta,
            DisenoFlash,
        ):
            modelo.objects.all().delete()
        tokens.EnlacePublico.objects.all().delete()
        self.stdout.write("Datos anteriores borrados.")

    def _estudio(self):
        a = AjustesEstudio.obtener()
        a.nombre = "ink_mels"
        a.nombre_artista = "Vale Ríos"
        a.eslogan = "Fine line y blackwork en Orlando"
        a.telefono = "(407) 555-0150"
        a.email = "hola@inkmels.example"
        a.direccion = "123 Ejemplo St, Orlando, FL 32801"
        a.instagram = "ink_mels"
        a.flash_publico = True
        a.ia_ejemplos = (
            "¡Hola, Maru! Qué ganas de verte el jueves 🖤 Recuerda venir comida y con ropa cómoda.\n"
            "Ey, ¿qué tal está curando? Si ves que se pela un poquito es normal, no lo rasques.\n"
            "Me encantó tatuarte hoy. Mándame foto cuando esté curado, que quiero verlo."
        )
        a.save()
        crear_predeterminados()
        if not HorarioLaboral.objects.exists():
            for dia in range(1, 6):
                HorarioLaboral.objects.create(dia_semana=dia, hora_inicio=time(11), hora_fin=time(19))
        for nombre in ("VIP", "Proyecto grande", "Prefiere tardes", "Viene con amigas"):
            Etiqueta.objects.get_or_create(nombre=nombre)
        if not tokens.enlace_estudio_vigente("reserva"):
            tokens.crear_enlace("reserva", dias=365)
        if not tokens.enlace_estudio_vigente("catalogo"):
            tokens.crear_enlace("catalogo", dias=365)

    def _clientes(self):
        hoy = timezone.localdate()
        etiquetas = {e.nombre: e for e in Etiqueta.objects.all()}
        clientes = []
        for i, (nombre, apellidos) in enumerate(NOMBRES):
            prefijo = self.r.choice(["407", "321", "689"])
            nacimiento = hoy.replace(year=hoy.year - self.r.randint(19, 52))
            if i == 3:  # Elena cumple hoy
                pass
            elif i == 6:
                nacimiento = nacimiento + timedelta(days=3)
            else:
                nacimiento = nacimiento - timedelta(days=self.r.randint(10, 340))
            c = Cliente.objects.create(
                nombre=nombre,
                apellidos=apellidos,
                telefono=f"+1{prefijo}55501{i:02d}",
                email=f"{nombre.lower().replace('í', 'i').replace('é', 'e').replace('á', 'a').replace('ó', 'o')}.{i}@correo.example",
                instagram=f"{nombre.lower()[:4]}{apellidos.lower()[:4]}" if self.r.random() < 0.6 else "",
                fecha_nacimiento=nacimiento if self.r.random() < 0.85 or i in (3, 6) else None,
                canal_preferido="sms" if self.r.random() < 0.25 else "whatsapp",
                origen=self.r.choice(["instagram", "instagram", "recomendacion", "web", "estudio"]),
                creado_en=timezone.now() - timedelta(days=self.r.randint(5, 560)),
                contacto_bloqueado=(i == 17),
            )
            if self.r.random() < 0.72 or i in (3, 5):
                c.dar_consentimiento(self.r.choice(["presencial", "formulario", "verbal"]))
            if i in (0, 4, 9, 22):
                c.etiquetas.add(etiquetas["VIP"])
            if i in (0, 4, 12):
                c.etiquetas.add(etiquetas["Proyecto grande"])
            if self.r.random() < 0.15:
                c.etiquetas.add(etiquetas["Prefiere tardes"])
            if i in (0, 8, 15):
                DatosSalud.objects.create(
                    cliente=c,
                    alergias="Látex" if i == 0 else "",
                    diabetes=i == 8,
                    condiciones_piel="Tendencia a queloides" if i == 15 else "",
                )
            clientes.append(c)
        return clientes

    def _tatuaje(self, c, n, terminado=True, fecha=None):
        estilo = self.r.choice(list(TITULOS))
        t = Tatuaje.objects.create(
            cliente=c,
            titulo=self.r.choice(TITULOS[estilo]),
            estilo=estilo,
            zona=self.r.choice(ZONAS),
            tamano=self.r.choice(TAMANOS),
            estado="terminado" if terminado else "en_proceso",
            fecha_inicio=fecha,
            fecha_fin=fecha if terminado else None,
            sesiones_previstas=self.r.choice([1, 1, 2, 3, 4]),
            precio_total=Decimal(self.r.choice([180, 250, 350, 600, 900, 1400])),
        )
        if n % 2 == 0:
            for tipo in ("referencia", "cicatrizado" if terminado else "resultado"):
                principal, mini = procesar_imagen(arte(n * 7 + len(tipo)), max_lado=1200, lado_miniatura=400)
                FotoTatuaje.objects.create(tatuaje=t, tipo=tipo, imagen=principal, miniatura=mini)
        return t

    def _agenda(self, clientes):
        hoy = timezone.localdate()
        tipos = {t.nombre: t for t in TipoCita.objects.all()}
        sesion, larga, consulta, retoque = tipos["Sesión"], tipos["Sesión larga"], tipos["Consulta"], tipos["Retoque"]
        ocupado: list[tuple] = []

        def hueco(fecha, hora, duracion):
            inicio = timezone.make_aware(datetime.combine(fecha, time(hora)))
            fin = inicio + timedelta(minutes=duracion)
            if fecha.weekday() in (0, 6) or any(i < fin and inicio < f for i, f in ocupado):
                return None
            ocupado.append((inicio, fin))
            return inicio, fin

        n = 0
        for i, c in enumerate(clientes):
            visitas = self.r.choice([0, 1, 1, 2, 2, 3, 4]) if i not in (0, 4) else 5
            if i in (5, 7, 11):  # clientes que se están alejando
                visitas = max(visitas, 2)
            ultima = None
            for v in range(visitas):
                dias_atras = self.r.randint(30, 540)
                if i in (5, 7, 11):
                    dias_atras = self.r.randint(220, 400)
                # Fechas elegidas para que la bandeja de hoy tenga ejemplos de cuidados
                if v == 0 and i in (4, 2, 9):
                    objetivo = {4: 1, 2: 14, 9: 30}[i]  # día 1, semana 2 y oferta de retoque
                    dias_atras = next(
                        d for d in range(objetivo, objetivo + 3) if (hoy - timedelta(days=d)).weekday() not in (0, 6)
                    )
                fecha = hoy - timedelta(days=dias_atras)
                tipo = self.r.choice([sesion, sesion, larga, retoque]) if v else self.r.choice([sesion, larga])
                franja = hueco(fecha, self.r.choice([11, 15]), tipo.duracion_minutos if tipo != larga else 240)
                if not franja:
                    continue
                n += 1
                t = self._tatuaje(c, n, terminado=True, fecha=fecha)
                estado = EstadoCita.REALIZADA if self.r.random() > 0.07 else EstadoCita.NO_SHOW
                cita = Cita.objects.create(
                    cliente=c,
                    tipo=tipo,
                    tatuaje=t,
                    inicio=franja[0],
                    fin=franja[1],
                    estado=estado,
                    precio=t.precio_total,
                    descripcion=f"Sesión de {t.titulo.lower()}",
                )
                if estado == EstadoCita.REALIZADA:
                    Pago.objects.create(
                        cliente=c,
                        cita=cita,
                        tatuaje=t,
                        tipo="sesion",
                        importe=t.precio_total,
                        fecha=fecha,
                        metodo=self.r.choice(["efectivo", "tarjeta", "zelle", "venmo", "cash_app"]),
                    )
                    if self.r.random() < 0.3:
                        NotaCliente.objects.create(
                            cliente=c,
                            cita=cita,
                            origen="sesion",
                            texto=self.r.choice(
                                [
                                    "Aguantó genial, sin pausas.",
                                    "Piel fina en la zona, ir suave.",
                                    "Quiere seguir con el brazo en primavera.",
                                    "Prefiere música tranquila.",
                                ]
                            ),
                        )
                ultima = fecha
            if i == 3:  # Elena: aniversario hoy
                hace_un_anio = hoy.replace(year=hoy.year - 1)
                Tatuaje.objects.create(
                    cliente=c,
                    titulo="Golondrina tradicional",
                    estilo="tradicional",
                    zona="antebrazo",
                    tamano="pequeno",
                    estado="terminado",
                    fecha_inicio=hace_un_anio,
                    fecha_fin=hace_un_anio,
                )
            _ = ultima

        # Próximas 3 semanas
        futuras = [
            (0, 12, clientes[0], larga, "confirmada"),
            (0, 19, clientes[1], consulta, "solicitada"),
            (1, 11, clientes[2], retoque, "confirmada"),
            (2, 11, clientes[12], larga, "confirmada"),
            (2, 16, clientes[13], consulta, "confirmada"),
            (3, 12, clientes[14], sesion, "solicitada"),
            (6, 11, clientes[15], sesion, "confirmada"),
            (7, 15, clientes[16], sesion, "confirmada"),
            (8, 11, clientes[18], larga, "confirmada"),
            (9, 14, clientes[19], sesion, "solicitada"),
            (13, 12, clientes[20], sesion, "confirmada"),
            (15, 11, clientes[21], larga, "confirmada"),
            (16, 15, clientes[23], consulta, "confirmada"),
            (20, 12, clientes[24], sesion, "confirmada"),
        ]
        for dias, hora, c, tipo, estado in futuras:
            fecha = hoy + timedelta(days=dias)
            while fecha.weekday() in (0, 6):
                fecha += timedelta(days=1)
            franja = hueco(fecha, hora, tipo.duracion_minutos)
            if not franja:
                continue
            t = self._tatuaje(c, self.r.randint(100, 999), terminado=False) if tipo != consulta else None
            cita = Cita.objects.create(
                cliente=c,
                tipo=tipo,
                tatuaje=t,
                inicio=franja[0],
                fin=franja[1],
                estado=estado,
                precio=t.precio_total if t else None,
                descripcion=t.titulo if t else "Consulta de idea",
            )
            if tipo.deposito_sugerido and estado == "confirmada":
                Pago.objects.create(
                    cliente=c,
                    cita=cita,
                    tatuaje=t,
                    tipo="sena",
                    importe=tipo.deposito_sugerido,
                    fecha=hoy - timedelta(days=self.r.randint(1, 10)),
                    metodo=self.r.choice(["zelle", "venmo"]),
                )
        c = Cita.objects.filter(estado="confirmada", inicio__gt=timezone.now()).order_by("inicio")[3]
        c.reprogramacion_pedida = "¿Podríamos pasarla a un sábado por la mañana?"
        c.reprogramacion_pedida_en = timezone.now() - timedelta(hours=5)
        c.save()

        inicio_bloqueo = timezone.make_aware(datetime.combine(hoy + timedelta(days=24), time.min))
        Bloqueo.objects.create(
            tipo="evento", motivo="Convención de Tampa", inicio=inicio_bloqueo, fin=inicio_bloqueo + timedelta(days=2)
        )
        for c, dias, franja in (
            (clientes[25], [5], "manana"),
            (clientes[26], [], "tarde"),
            (clientes[27], [2, 3], "cualquiera"),
        ):
            EntradaListaEspera.objects.create(
                cliente=c, tipo=sesion, dias=dias, franja=franja, notas="Avisar si se libera algo"
            )

    def _finanzas(self):
        hoy = timezone.localdate()
        for m in range(0, 13):
            mes = (hoy.replace(day=1) - timedelta(days=m * 30)).replace(day=1)
            Gasto.objects.create(
                fecha=mes,
                categoria="alquiler",
                concepto="Alquiler del local",
                importe=Decimal("1200"),
                metodo="transferencia",
            )
            Gasto.objects.create(
                fecha=mes + timedelta(days=4),
                categoria="material",
                concepto="Agujas, tintas y film",
                importe=Decimal(self.r.randint(180, 420)),
                metodo="tarjeta",
            )
            Gasto.objects.create(
                fecha=mes + timedelta(days=9),
                categoria="suministros",
                concepto="Luz e internet",
                importe=Decimal(self.r.randint(110, 170)),
                metodo="tarjeta",
            )
            if m % 3 == 0:
                Gasto.objects.create(
                    fecha=mes + timedelta(days=12),
                    categoria="marketing",
                    concepto="Anuncios de Instagram",
                    importe=Decimal("90"),
                    metodo="tarjeta",
                )

    def _flash(self):
        disenos = [
            ("Luna mística", 180, "disponible"),
            ("Daga y rosa", 250, "disponible"),
            ("Polilla nocturna", 220, "disponible"),
            ("Ojo que todo lo ve", 150, "reservado"),
            ("Serpiente ornamental", 300, "vendido"),
            ("Mano y estrellas", 200, "disponible"),
            ("Calavera floral", 280, "disponible"),
            ("Ola minimal", 120, "disponible"),
        ]
        for i, (titulo, precio, estado) in enumerate(disenos):
            principal, mini = procesar_imagen(arte(500 + i), max_lado=1200, lado_miniatura=500)
            DisenoFlash.objects.create(
                titulo=titulo,
                precio=precio,
                tamano=self.r.choice(["6 × 6 cm", "8 × 10 cm", "10 × 12 cm"]),
                estado=estado,
                imagen=principal,
                miniatura=mini,
                orden=i,
                repetible=i % 3 == 0,
                zona_sugerida=self.r.choice(ZONAS),
            )

    def _solicitudes(self):
        ideas = [
            (
                "Abril",
                "Montero",
                "Quiero una rama de olivo fina rodeando la muñeca, solo línea negra, algo delicado.",
                "mano",
                "pequeno",
                "fine_line",
            ),
            (
                "Jake",
                "Holloway",
                "Me gustaría un cover-up de un tribal viejo en el hombro con algo de blackwork, tipo mandala o geometría.",
                "hombro",
                "grande",
                "blackwork",
            ),
            (
                "Lorena",
                "Pizarro",
                "Un retrato de mi perro en realismo, tengo varias fotos. ¿Cuántas sesiones serían?",
                "muslo",
                "mediano",
                "realismo",
            ),
            ("Kayla", "Moss", "Flash de la luna que vi en tu catálogo, en el tobillo.", "tobillo", "mini", "fine_line"),
        ]
        hoy = timezone.localdate()
        for i, (nombre, apellidos, desc, zona, tamano, estilo) in enumerate(ideas):
            s = SolicitudReserva.objects.create(
                nombre=nombre,
                apellidos=apellidos,
                telefono=f"+1407555019{i}",
                email=f"{nombre.lower()}@correo.example",
                fecha_nacimiento=hoy.replace(year=hoy.year - 24 - i),
                descripcion=desc,
                zona=zona,
                tamano=tamano,
                estilo=estilo,
                fechas_preferidas=self.r.choice(["Tardes entre semana", "Sábados", "Cualquier día de enero"]),
                acepta_marketing=i % 2 == 0,
                primer_tatuaje=i == 0,
                creado_en=timezone.now() - timedelta(hours=self.r.randint(2, 70)),
            )
            for j in range(2 if i < 3 else 1):
                principal, mini = procesar_imagen(arte(900 + i * 10 + j), max_lado=1200, lado_miniatura=400)
                ImagenSolicitud.objects.create(solicitud=s, imagen=principal, miniatura=mini)

    def _historial_mensajes(self, clientes):
        plantilla = Plantilla.para(Categoria.CUIDADO)
        for c in clientes[:18]:
            if c.contacto_bloqueado:
                continue
            for k in range(self.r.randint(1, 3)):
                cuando = timezone.now() - timedelta(days=self.r.randint(2, 200), hours=self.r.randint(0, 8))
                MensajePreparado.objects.create(
                    cliente=c,
                    tipo=Categoria.CUIDADO,
                    clave=f"demo:{c.pk}:{k}",
                    plantilla=plantilla,
                    texto=f"Hola {c.nombre} 🖤 ¿Qué tal ese tatuaje? Lávalo con agua tibia y crema fina. Cualquier duda, escríbeme.",
                    motivo="Cuidados (demo)",
                    fecha_programada=cuando.date(),
                    estado="enviado",
                    enviado_en=cuando,
                    canal_usado=self.r.choice(["whatsapp_link", "whatsapp_link", "sms_link", "copia"]),
                )

    def _consentimientos(self, clientes):
        from apps.clientes.consentimiento import registrar

        for c in clientes:
            cita = c.citas.filter(estado="realizada").order_by("-inicio").first()
            registrar(
                c,
                cita=cita,
                nombre=c.nombre_completo,
                fecha_nacimiento=c.fecha_nacimiento or timezone.localdate().replace(year=1990),
                salud={
                    "alergias": "Látex" if c.nombre == "Lucía" else "",
                    "medicacion": "",
                    "anticoagulantes": False,
                    "diabetes": False,
                    "epilepsia": False,
                    "problemas_cardiacos": False,
                    "embarazo_lactancia": False,
                    "condiciones_piel": "",
                    "otras": "",
                },
                firma_data_url=firma_png(),
                autoriza_fotos=True,
                acepta_marketing=c.marketing_consentimiento,
                ip="127.0.0.1",
            )
