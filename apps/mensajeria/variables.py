"""Variables de plantilla: {nombre}, {fecha_cita}, {zona}…"""

import re
from datetime import date

from django.urls import reverse
from django.utils import timezone

from apps.nucleo import tokens
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.templatetags.ui import fecha_larga, hora

PATRON = re.compile(r"\{([a-z_]+)\}")

VARIABLES = {
    "nombre": "Nombre del cliente",
    "nombre_completo": "Nombre y apellidos",
    "estudio": "Nombre del estudio",
    "artista": "Tu nombre",
    "fecha_cita": "Día de la cita (jueves 27 de noviembre)",
    "hora_cita": "Hora de la cita (3:30 pm)",
    "tipo_cita": "Tipo de cita",
    "enlace_cita": "Enlace para confirmar, cancelar o cambiar la cita",
    "tatuaje": "Título del tatuaje",
    "zona": "Zona del tatuaje",
    "aniversario": "Tiempo desde el tatuaje (1 año)",
    "dias_sesion": "Días desde la sesión",
    "fecha_destacada": "Nombre de la fecha destacada",
    "enlace_reserva": "Enlace a tu página de reservas",
    "instagram": "Tu Instagram (@usuario)",
    "telefono_estudio": "Teléfono del estudio",
    "direccion": "Dirección del estudio",
    "cuidados": "Texto de cuidados generales",
}


def desconocidas(cuerpo: str) -> list[str]:
    return sorted({v for v in PATRON.findall(cuerpo or "") if v not in VARIABLES})


def renderizar(cuerpo: str, contexto: dict) -> str:
    """Sustituye las variables conocidas; las que falten se quedan tal cual
    para que se vean en la vista previa y se puedan corregir."""

    def sustituir(m):
        valor = contexto.get(m.group(1))
        if callable(valor):
            valor = valor()
        return m.group(0) if valor in (None, "") else str(valor)

    return PATRON.sub(sustituir, cuerpo or "").strip()


def _tiempo(desde: date, hasta: date) -> str:
    anios = hasta.year - desde.year - ((hasta.month, hasta.day) < (desde.month, desde.day))
    if anios >= 1:
        return "1 año" if anios == 1 else f"{anios} años"
    meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month
    return "1 mes" if meses <= 1 else f"{meses} meses"


def _enlace_reserva() -> str:
    """Enlace vigente a la página de reservas; si no hay ninguno, se crea (1 año)."""
    enlace = tokens.enlace_estudio_vigente(tokens.EnlacePublico.Proposito.RESERVA)
    if not enlace:
        enlace, _ = tokens.crear_enlace(tokens.EnlacePublico.Proposito.RESERVA, dias=365)
    try:
        return tokens.url_absoluta(reverse("reserva_publica", args=[enlace.token_visible]))
    except Exception:
        return ""


def contexto(cliente, *, cita=None, tatuaje=None, fecha_destacada=None, hoy: date | None = None) -> dict:
    """Contexto de variables. Los valores costosos (enlaces) se calculan solo si se usan."""
    hoy = hoy or timezone.localdate()
    ajustes = AjustesEstudio.obtener()
    tatuaje = tatuaje or (cita.tatuaje if cita else None)
    datos = {
        "nombre": cliente.nombre,
        "nombre_completo": cliente.nombre_completo,
        "estudio": ajustes.nombre,
        "artista": ajustes.firma,
        "instagram": f"@{ajustes.instagram}" if ajustes.instagram else "",
        "telefono_estudio": ajustes.telefono,
        "direccion": ajustes.direccion,
        "cuidados": ajustes.texto_cuidados,
        "enlace_reserva": _enlace_reserva,
        "fecha_destacada": fecha_destacada.nombre if fecha_destacada else "",
    }
    if cita is not None:
        from apps.agenda.servicios import enlace_cita

        datos.update(
            fecha_cita=fecha_larga(cita.inicio),
            hora_cita=hora(cita.inicio),
            tipo_cita=cita.tipo.nombre,
            enlace_cita=lambda: enlace_cita(cita),
            dias_sesion=(hoy - timezone.localtime(cita.inicio).date()).days,
        )
    if tatuaje is not None:
        datos.update(tatuaje=tatuaje.titulo, zona=tatuaje.get_zona_display().lower() if tatuaje.zona else "")
        if tatuaje.fecha_aniversario:
            datos["aniversario"] = _tiempo(tatuaje.fecha_aniversario, hoy)
    return datos


def contexto_ejemplo() -> dict:
    """Para la vista previa de plantillas."""
    ajustes = AjustesEstudio.obtener()
    return {
        "nombre": "Lucía",
        "nombre_completo": "Lucía Méndez",
        "estudio": ajustes.nombre,
        "artista": ajustes.firma,
        "fecha_cita": "jueves 27 de noviembre",
        "hora_cita": "3:30 pm",
        "tipo_cita": "Sesión",
        "enlace_cita": "https://tu-estudio.onrender.com/c/…",
        "tatuaje": "Manga botánica",
        "zona": "antebrazo",
        "aniversario": "1 año",
        "dias_sesion": 3,
        "fecha_destacada": "Navidad",
        "enlace_reserva": _enlace_reserva() or "https://tu-estudio.onrender.com/r/…",
        "instagram": f"@{ajustes.instagram}" if ajustes.instagram else "@tuestudio",
        "telefono_estudio": ajustes.telefono or "(407) 555-0100",
        "direccion": ajustes.direccion or "Calle Ejemplo 123",
        "cuidados": ajustes.texto_cuidados,
    }
