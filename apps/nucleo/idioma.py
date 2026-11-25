"""Idiomas: la interfaz sigue a cada persona; el contenido para clientes, al estudio.

- Interfaz: la elige cada usuaria (selector ES/EN, cookie) o el navegador.
- Contenido (mensajes, consentimiento, textos legales, plantillas de partida):
  idioma del estudio = ``settings.LANGUAGE_CODE`` (variable de entorno IDIOMA).
"""

from django.conf import settings
from django.utils import translation

NOMBRES_IA = {
    "es": "español neutro, tuteo",
    "en": "inglés de EE. UU., cercano y natural (usa «you», sin formalismos)",
}


def contenido():
    """Contexto para escribir texto que leerán las clientas, en el idioma del estudio."""
    return translation.override(settings.LANGUAGE_CODE)


def idioma_ia(codigo: str | None) -> str:
    """Cómo pedirle a la IA que escriba en ese idioma."""
    base = (codigo or settings.LANGUAGE_CODE).split("-")[0]
    return NOMBRES_IA.get(base, NOMBRES_IA["es"])
