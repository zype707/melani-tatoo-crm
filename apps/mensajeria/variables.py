"""Variables de plantilla: {nombre}, {fecha_cita}, {zona}…"""

import re
from datetime import date

from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from apps.nucleo import tokens
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.templatetags.ui import fecha_larga, hora

PATRON = re.compile(r"\{([a-z_]+)\}")

VARIABLES = {
    "nombre": gettext_lazy("Nombre del cliente"),
    "nombre_completo": gettext_lazy("Nombre y apellidos"),
    "estudio": gettext_lazy("Nombre del estudio"),
    "artista": gettext_lazy("Tu nombre"),
    "fecha_cita": gettext_lazy("Día de la cita (jueves 27 de noviembre)"),
    "hora_cita": gettext_lazy("Hora de la cita (3:30 pm)"),
    "tipo_cita": gettext_lazy("Tipo de cita"),
    "enlace_cita": gettext_lazy("Enlace para confirmar, cancelar o cambiar la cita"),
    "tatuaje": gettext_lazy("Título del tatuaje"),
    "zona": gettext_lazy("Zona del tatuaje"),
    "aniversario": gettext_lazy("Tiempo desde el tatuaje (1 año)"),
    "dias_sesion": gettext_lazy("Días desde la sesión"),
    "fecha_destacada": gettext_lazy("Nombre de la fecha destacada"),
    "enlace_reserva": gettext_lazy("Enlace a tu página de reservas"),
    "instagram": gettext_lazy("Tu Instagram (@usuario)"),
    "telefono_estudio": gettext_lazy("Teléfono del estudio"),
    "direccion": gettext_lazy("Dirección del estudio"),
    "cuidados": gettext_lazy("Texto de cuidados generales"),
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
        return ngettext("%(n)d año", "%(n)d años", anios) % {"n": anios}
    meses = max(1, (hasta.year - desde.year) * 12 + hasta.month - desde.month)
    return ngettext("%(n)d mes", "%(n)d meses", meses) % {"n": meses}


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
    """Contexto de variables. Los valores costosos (enlaces) se calculan solo si se usan.

    Los valores van dentro de mensajes para clientes, así que se escriben en el idioma
    del contenido (IDIOMA / LANGUAGE_CODE), no en el idioma de la interfaz de quien mira.
    """
    with translation.override(settings.LANGUAGE_CODE):
        return _contexto(cliente, cita=cita, tatuaje=tatuaje, fecha_destacada=fecha_destacada, hoy=hoy)


def _contexto(cliente, *, cita, tatuaje, fecha_destacada, hoy) -> dict:
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
    """Para la vista previa de plantillas (en el idioma del contenido)."""
    ajustes = AjustesEstudio.obtener()
    with translation.override(settings.LANGUAGE_CODE):
        return {
            "nombre": "Lucía",
            "nombre_completo": "Lucía Méndez",
            "estudio": ajustes.nombre,
            "artista": ajustes.firma,
            "fecha_cita": _("jueves 27 de noviembre"),
            "hora_cita": "3:30 pm",
            "tipo_cita": _("Sesión"),
            "enlace_cita": "https://tu-estudio.onrender.com/c/…",
            "tatuaje": _("Manga botánica"),
            "zona": _("antebrazo"),
            "aniversario": ngettext("%(n)d año", "%(n)d años", 1) % {"n": 1},
            "dias_sesion": 3,
            "fecha_destacada": _("Navidad"),
            "enlace_reserva": _enlace_reserva() or "https://tu-estudio.onrender.com/r/…",
            "instagram": f"@{ajustes.instagram}" if ajustes.instagram else "@tuestudio",
            "telefono_estudio": ajustes.telefono or "(407) 555-0100",
            "direccion": ajustes.direccion or _("Calle Ejemplo 123"),
            "cuidados": ajustes.texto_cuidados,
        }
