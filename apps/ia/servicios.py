"""Funciones de IA. La IA propone; la usuaria decide. Nada se envía solo."""

import json
import time

from django.conf import settings
from django.utils import timezone

from apps.clientes.models import Tatuaje
from apps.nucleo.models import AjustesEstudio

from . import proveedor
from .models import UsoIA
from .privacidad import perfil_cliente, redactar_pii
from .proveedor import ErrorIA

Funcion = UsoIA.Funcion


def disponible() -> bool:
    return bool(settings.OPENAI_API_KEY or proveedor._proveedor_pruebas) and AjustesEstudio.obtener().ia_activa


def usos_del_mes() -> int:
    hoy = timezone.localdate()
    return UsoIA.objects.filter(creado_en__year=hoy.year, creado_en__month=hoy.month).count()


def estado() -> dict:
    ajustes = AjustesEstudio.obtener()
    return {
        "configurada": bool(settings.OPENAI_API_KEY),
        "activa": ajustes.ia_activa,
        "modelo": settings.IA_MODELO,
        "usos": usos_del_mes(),
        "limite": ajustes.limite_ia,
    }


def _comprobar() -> None:
    if not disponible():
        raise ErrorIA("El asistente de IA no está activado.", "no_configurada")
    if usos_del_mes() >= AjustesEstudio.obtener().limite_ia:
        raise ErrorIA("Has llegado al límite mensual de consultas de IA. Puedes subirlo en Ajustes.", "cuota")


def _ejecutar(funcion: str, usuario, llamada):
    _comprobar()
    inicio = time.monotonic()
    uso = UsoIA(funcion=funcion, usuario=usuario if getattr(usuario, "pk", None) else None)
    try:
        salida, resultado = llamada(proveedor.obtener())
        uso.exito = True
        uso.tokens_entrada, uso.tokens_salida = resultado.tokens_entrada, resultado.tokens_salida
        return salida
    except ErrorIA as exc:
        uso.error = exc.codigo
        raise
    finally:
        uso.duracion_ms = int((time.monotonic() - inicio) * 1000)
        uso.save()


def _voz() -> str:
    a = AjustesEstudio.obtener()
    ejemplos = redactar_pii(a.ia_ejemplos, 2500)
    partes = [
        f"Escribes en nombre de {a.firma}, tatuadora de {a.nombre} (Orlando, Florida).",
        "Idioma: español neutro, tuteo. Mensajes para WhatsApp o SMS: breves (2-4 frases), cálidos y directos.",
        f"Tono: {a.ia_tono or 'cercano y profesional'}",
        "Reglas: no inventes precios, fechas, ofertas ni enlaces que no te den. Nunca menciones salud ni datos médicos. "
        "Como mucho un emoji. Sin firmas tipo 'Atentamente'. Devuelve solo el texto del mensaje.",
    ]
    if ejemplos:
        partes.append("Ejemplos de cómo escribe (imita el estilo, no copies el contenido):\n" + ejemplos)
    return "\n".join(partes)


def _texto(instrucciones: str, entrada: str, max_tokens: int):
    """Adaptador para _ejecutar: llamada de texto libre."""

    def llamada(p):
        r = p.texto(instrucciones, entrada, max_tokens)
        return r.texto, r

    return llamada


def _datos(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False, default=str)


# --- 1. Redactor de mensajes ------------------------------------------------------------------


def redactar_mensaje(cliente, objetivo: str, instrucciones: str = "", borrador: str = "", usuario=None) -> str:
    _comprobar()
    entrada = _datos(
        objetivo=objetivo,
        indicaciones=redactar_pii(instrucciones, 500),
        borrador_actual=redactar_pii(borrador, 1500),
        cliente=perfil_cliente(cliente),
    )
    return _ejecutar(
        Funcion.REDACTAR, usuario, _texto(_voz() + "\nRedacta el mensaje para este cliente.", entrada, 400)
    )


# --- 2. Triaje de solicitudes ---------------------------------------------------------------


def _enum(choices) -> list[str]:
    return [v for v, _ in choices] + ["desconocido"]


ESQUEMA_TRIAJE = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "resumen",
        "estilo",
        "zona",
        "tamano",
        "sesiones_estimadas",
        "horas_estimadas",
        "complejidad",
        "preguntas",
    ],
    "properties": {
        "resumen": {"type": "string", "description": "Una frase que resuma la idea."},
        "estilo": {"type": "string", "enum": _enum(Tatuaje.Estilo.choices)},
        "zona": {"type": "string", "enum": _enum(Tatuaje.Zona.choices)},
        "tamano": {"type": "string", "enum": _enum(Tatuaje.Tamano.choices)},
        "sesiones_estimadas": {"type": "integer"},
        "horas_estimadas": {"type": "number"},
        "complejidad": {"type": "string", "enum": ["baja", "media", "alta"]},
        "preguntas": {"type": "array", "items": {"type": "string"}, "description": "Lo que falta preguntar."},
    },
}


def triaje_solicitud(solicitud, usuario=None) -> dict:
    _comprobar()
    entrada = _datos(
        descripcion=redactar_pii(solicitud.descripcion, 2500),
        zona_declarada=solicitud.get_zona_display() if solicitud.zona else "",
        tamano_declarado=solicitud.get_tamano_display() if solicitud.tamano else "",
        estilo_declarado=solicitud.get_estilo_display() if solicitud.estilo else "",
        medidas=redactar_pii(solicitud.medidas, 60),
        primer_tatuaje=solicitud.primer_tatuaje,
        imagenes_de_referencia=solicitud.imagenes.count(),
    )
    instrucciones = (
        "Eres la asistente de una tatuadora profesional. Estructura la solicitud de tatuaje. "
        "Estima sesiones y horas de forma prudente para una tatuadora experimentada. "
        "En 'preguntas' lista en español (tuteo) lo que falta para presupuestar: tamaño exacto, color o negro, "
        "ubicación precisa, referencias, disponibilidad… Máximo 5. Si un dato no se deduce, usa 'desconocido'."
    )
    datos = _ejecutar(
        Funcion.TRIAJE, usuario, lambda p: p.json(instrucciones, entrada, "triaje_tatuaje", ESQUEMA_TRIAJE)
    )
    solicitud.triaje = datos
    solicitud.triaje_en = timezone.now()
    solicitud.save(update_fields=["triaje", "triaje_en"])
    return datos


# --- 3. Resumen previo a la cita ------------------------------------------------------------


def resumen_cita(cita, usuario=None) -> str:
    _comprobar()
    entrada = _datos(
        cita={
            "tipo": cita.tipo.nombre,
            "duracion_min": cita.duracion_minutos,
            "estado": cita.get_estado_display(),
            "que_se_hace": redactar_pii(cita.descripcion, 200),
            "precio_previsto": str(cita.precio or ""),
            "pagado": str(cita.pagado),
        },
        proyecto=(
            {
                "titulo": redactar_pii(cita.tatuaje.titulo, 80),
                "estado": cita.tatuaje.get_estado_display(),
                "sesiones_previstas": cita.tatuaje.sesiones_previstas,
                "sesiones_hechas": cita.tatuaje.sesiones_realizadas,
            }
            if cita.tatuaje
            else None
        ),
        cliente=perfil_cliente(cita.cliente),
    )
    instrucciones = (
        "Prepara una ficha rápida para la tatuadora antes de la cita: 3-5 viñetas breves en español con quién viene, "
        "qué se hace hoy, cómo va el proyecto y qué recordar (seña o pago pendiente, si repite, etc.). "
        "No hables de salud. No inventes datos."
    )
    return _ejecutar(Funcion.RESUMEN, usuario, _texto(instrucciones, entrada, 350))


# --- 4. Sugerencias de retención ------------------------------------------------------------

ESQUEMA_RETENCION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ideas", "mensaje"],
    "properties": {
        "ideas": {"type": "array", "items": {"type": "string"}},
        "mensaje": {"type": "string"},
    },
}


def sugerencias_retencion(cliente, usuario=None) -> dict:
    _comprobar()
    entrada = _datos(cliente=perfil_cliente(cliente))
    instrucciones = (
        _voz() + "\nEste cliente lleva tiempo sin venir. Da 3 ideas concretas y realistas para recuperarlo "
        "(sin descuentos agresivos) y un mensaje corto listo para enviar. Si no acepta promociones, el mensaje "
        "debe ser de seguimiento del tatuaje, nunca promocional."
    )
    return _ejecutar(
        Funcion.RETENCION, usuario, lambda p: p.json(instrucciones, entrada, "retencion", ESQUEMA_RETENCION)
    )


# --- 5. Búsqueda en lenguaje natural -----------------------------------------------------------


def interpretar_busqueda(frase: str, usuario=None) -> dict:
    _comprobar()
    from .busqueda import ESQUEMA, INSTRUCCIONES

    return _ejecutar(
        Funcion.BUSQUEDA,
        usuario,
        lambda p: p.json(INSTRUCCIONES, redactar_pii(frase, 300), "filtros_busqueda", ESQUEMA, 400),
    )


# --- 6. Respuesta sugerida --------------------------------------------------------------------


def respuesta_sugerida(texto_recibido: str, cliente=None, indicaciones: str = "", usuario=None) -> str:
    _comprobar()
    entrada = _datos(
        mensaje_recibido=redactar_pii(texto_recibido, 2000),
        indicaciones=redactar_pii(indicaciones, 400),
        cliente=perfil_cliente(cliente) if cliente else None,
    )
    instrucciones = _voz() + (
        "\nTe paso un mensaje que ha recibido la tatuadora. Propón una respuesta. Si preguntan precio o fecha y no "
        "los tienes, responde que lo confirmas enseguida en lugar de inventarlo."
    )
    return _ejecutar(Funcion.RESPUESTA, usuario, _texto(instrucciones, entrada, 400))
