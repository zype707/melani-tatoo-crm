"""Contenido inicial del estudio: plantillas, cuidados, fechas destacadas (EE. UU.)
y tipos de cita. Se crea una sola vez con `manage.py inicializar_estudio`."""

from datetime import time

from django.conf import settings
from django.db import transaction

from .models import Categoria, FechaDestacada, PasoCuidado, Plantilla

PLANTILLAS = [
    # (clave interna, nombre, categoría, promocional, texto)
    (
        "recordatorio",
        "Recordatorio de cita",
        Categoria.RECORDATORIO,
        False,
        "¡Hola {nombre}! Te recuerdo tu cita en {estudio} el {fecha_cita} a las {hora_cita}. "
        "Si necesitas confirmarla, cambiarla o cancelarla, puedes hacerlo aquí: {enlace_cita}\n¡Nos vemos!",
    ),
    (
        "dia1",
        "Cuidados · día 1",
        Categoria.CUIDADO,
        False,
        "Hola {nombre} 🖤 ¿Qué tal ese tatuaje? Hoy toca lavarlo con agua tibia y jabón neutro, secarlo a toques "
        "y ponerle una capa fina de crema. Cualquier duda, escríbeme.",
    ),
    (
        "dia3",
        "Cuidados · día 3",
        Categoria.CUIDADO,
        False,
        "¡Hola {nombre}! Día 3: es normal que pique o se pele un poco. No rasques ni arranques nada y sigue con la "
        "crema en capa fina. ¿Cómo lo ves?",
    ),
    (
        "semana2",
        "Cuidados · semana 2",
        Categoria.CUIDADO,
        False,
        "{nombre}, ya van dos semanas desde tu tatuaje. Si está cicatrizando bien, ¿me mandas una foto? "
        "Me encanta ver cómo queda.",
    ),
    (
        "retoque",
        "Oferta de retoque (30 días)",
        Categoria.RETOQUE,
        False,
        "Hola {nombre}, ya ha pasado un mes desde tu tatuaje. Si ves alguna zona que necesite retoque, "
        "escríbeme y buscamos un hueco. El retoque está incluido.",
    ),
    (
        "hueco",
        "Hueco libre para la lista de espera",
        Categoria.LISTA_ESPERA,
        False,
        "¡Hola {nombre}! Se me ha liberado un hueco el {fecha_cita} a las {hora_cita}. ¿Te viene bien? "
        "Si me contestas pronto, te lo guardo.",
    ),
    (
        "aprobada",
        "Solicitud aceptada",
        Categoria.SOLICITUD,
        False,
        "¡Hola {nombre}! Gracias por escribirme, me encanta tu idea. ¿Qué días te vienen mejor? "
        "Te propongo fecha y te paso los detalles de la seña.",
    ),
    (
        "rechazada",
        "Solicitud no aceptada",
        Categoria.SOLICITUD,
        False,
        "Hola {nombre}, gracias por pensar en mí para tu tatuaje. Ahora mismo no puedo encargarme de ese proyecto, "
        "pero te deseo lo mejor con él.",
    ),
    (
        "cumple",
        "Feliz cumpleaños",
        Categoria.CUMPLEANOS,
        True,
        "¡Feliz cumpleaños, {nombre}! 🎉 Que tengas un día increíble. Un abrazo de {artista}.",
    ),
    (
        "aniversario",
        "Aniversario del tatuaje",
        Categoria.ANIVERSARIO,
        True,
        "{nombre}, ¡hoy hace {aniversario} de tu tatuaje «{tatuaje}»! Gracias por confiar en mí. "
        "Si tienes una foto de cómo está ahora, me encantaría verla.",
    ),
    (
        "reactivacion",
        "Te echamos de menos",
        Categoria.REACTIVACION,
        True,
        "¡Hola {nombre}! Hace tiempo que no nos vemos. Tengo huecos en las próximas semanas por si te apetece "
        "algo nuevo o un retoque. Cuéntame tu idea aquí: {enlace_reserva}",
    ),
    (
        "campana",
        "Flash disponible",
        Categoria.CAMPANA,
        True,
        "¡Hola {nombre}! Tengo diseños flash nuevos disponibles este mes. ¿Te mando el catálogo? {enlace_reserva}",
    ),
    (
        "navidad",
        "Navidad",
        Categoria.FECHA_DESTACADA,
        True,
        "¡Feliz Navidad, {nombre}! 🎄 Gracias por formar parte de este año en {estudio}.",
    ),
    (
        "anio_nuevo",
        "Año Nuevo",
        Categoria.FECHA_DESTACADA,
        True,
        "¡Feliz año nuevo, {nombre}! Que este año venga lleno de buenas ideas (y de tinta). — {artista}",
    ),
    (
        "san_valentin",
        "San Valentín",
        Categoria.FECHA_DESTACADA,
        True,
        "Feliz San Valentín, {nombre} 🖤 Este mes tengo diseños para parejas y amistades. ¿Te apuntas?",
    ),
    (
        "madre",
        "Día de la Madre",
        Categoria.FECHA_DESTACADA,
        True,
        "{nombre}, ¡feliz Día de la Madre! Si quieres regalar (o regalarte) un tatuaje, tengo tarjetas regalo.",
    ),
    (
        "padre",
        "Día del Padre",
        Categoria.FECHA_DESTACADA,
        True,
        "{nombre}, ¡feliz Día del Padre! Las tarjetas regalo del estudio son un buen plan para el domingo.",
    ),
    (
        "dia_tatuaje",
        "Día del Tatuaje",
        Categoria.FECHA_DESTACADA,
        True,
        "Hoy es el Día del Tatuaje 🖤 Gracias por llevar mi trabajo contigo, {nombre}.",
    ),
    (
        "halloween",
        "Halloween",
        Categoria.FECHA_DESTACADA,
        True,
        "¡Feliz Halloween, {nombre}! 🎃 Esta semana tengo diseños de temporada. ¿Te reservo uno?",
    ),
    (
        "gracias",
        "Acción de Gracias",
        Categoria.FECHA_DESTACADA,
        True,
        "Feliz Día de Acción de Gracias, {nombre}. Gracias por tu confianza este año.",
    ),
    (
        "viernes13",
        "Viernes 13",
        Categoria.FECHA_DESTACADA,
        True,
        "¡Viernes 13, {nombre}! 🔮 Flash especial solo hoy. Escríbeme para reservar tu hueco.",
    ),
]

CUIDADOS = [
    ("Día 1", 1, "dia1", False),
    ("Día 3", 3, "dia3", False),
    ("Semana 2", 14, "semana2", False),
    ("Retoque", 30, "retoque", True),
]

FECHAS = [
    # nombre, regla, mes, dia, semana, dia_semana, ventana, plantilla, activa
    ("Año Nuevo", "fija", 1, 1, None, None, 1, "anio_nuevo", True),
    ("San Valentín", "fija", 2, 14, None, None, 5, "san_valentin", True),
    ("Día de la Madre (EE. UU.)", "nth", 5, None, 2, 6, 5, "madre", True),
    ("Día del Padre (EE. UU.)", "nth", 6, None, 3, 6, 5, "padre", True),
    ("Día Nacional del Tatuaje", "fija", 7, 17, None, None, 1, "dia_tatuaje", True),
    ("Halloween", "fija", 10, 31, None, None, 3, "halloween", True),
    ("Acción de Gracias", "nth", 11, None, 4, 3, 1, "gracias", True),
    ("Navidad", "fija", 12, 25, None, None, 2, "navidad", True),
    ("Viernes 13 (flash day)", "viernes13", None, None, None, None, 1, "viernes13", False),
]


def _en_idioma(idioma: str):
    """Devuelve las listas de contenido en el idioma del estudio (es por defecto, o en)."""
    if not idioma.startswith("en"):
        return PLANTILLAS, CUIDADOS, FECHAS, {}
    from . import predeterminados_en as en

    plantillas = [(c, *en.PLANTILLAS[c][:1], cat, promo, en.PLANTILLAS[c][1]) for c, _n, cat, promo, _t in PLANTILLAS]
    cuidados = [(en.CUIDADOS[clave], dias, clave, retoque) for _n, dias, clave, retoque in CUIDADOS]
    fechas = [(en.FECHAS[f[7]], *f[1:]) for f in FECHAS]
    return plantillas, cuidados, fechas, en.TIPOS


@transaction.atomic
def crear_predeterminados(idioma: str | None = None) -> dict:
    """Crea el contenido inicial en el idioma del estudio (IDIOMA / LANGUAGE_CODE)."""
    creado = {"plantillas": 0, "cuidados": 0, "fechas": 0, "tipos": 0, "horario": 0}
    if Plantilla.objects.exists():
        return creado
    plantillas, cuidados, fechas, tipos_traducidos = _en_idioma(idioma or settings.LANGUAGE_CODE)
    por_clave = {}
    vistas = set()
    for clave, nombre, categoria, promo, texto in plantillas:
        por_clave[clave] = Plantilla.objects.create(
            nombre=nombre,
            categoria=categoria,
            es_promocional=promo,
            cuerpo=texto,
            predeterminada=categoria not in vistas,
        )
        vistas.add(categoria)
        creado["plantillas"] += 1
    for nombre, dias, clave, retoque in cuidados:
        PasoCuidado.objects.create(
            nombre=nombre, dias_despues=dias, plantilla=por_clave[clave], es_oferta_retoque=retoque
        )
        creado["cuidados"] += 1
    for nombre, regla, mes, dia, semana, dsem, ventana, clave, activa in fechas:
        FechaDestacada.objects.create(
            nombre=nombre,
            regla=regla,
            mes=mes,
            dia=dia,
            semana=semana,
            dia_semana=dsem,
            dias_ventana=ventana,
            plantilla=por_clave[clave],
            activa=activa,
        )
        creado["fechas"] += 1

    from apps.agenda.models import HorarioLaboral, TipoCita

    if not TipoCita.objects.exists():
        for orden, (nombre, cat, minutos, color, sena) in enumerate(
            [
                ("Consulta", "consulta", 30, "cielo", None),
                ("Sesión", "sesion", 180, "hueso", 100),
                ("Sesión larga", "sesion", 360, "lila", 200),
                ("Retoque", "retoque", 60, "menta", None),
            ]
        ):
            TipoCita.objects.create(
                nombre=tipos_traducidos.get(nombre, nombre),
                categoria=cat,
                duracion_minutos=minutos,
                color=color,
                deposito_sugerido=sena,
                orden=orden,
            )
            creado["tipos"] += 1
    if not HorarioLaboral.objects.exists():
        for dia in range(1, 6):  # martes a sábado
            HorarioLaboral.objects.create(dia_semana=dia, hora_inicio=time(11), hora_fin=time(19))
            creado["horario"] += 1
    return creado
