"""Capa de canales de envío.

Hoy ningún canal envía nada por sí solo: preparan un enlace (`wa.me`, `sms:`)
o el texto para copiar, y la tatuadora envía con un toque desde su móvil.

Para conectar en el futuro la API oficial de WhatsApp Business basta con
añadir una subclase con `envia_solo = True` que implemente `enviar()` y
registrarla en `REGISTRO`. El resto de la app (bandeja, historial, campañas)
no cambia: trabaja con `Canal` y `AccionEnvio`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import quote

from django.utils.translation import gettext as _

from .models import Canal as CanalChoices


@dataclass(frozen=True)
class AccionEnvio:
    canal: str
    etiqueta: str
    icono: str
    url: str | None  # None = copiar al portapapeles
    base: str | None  # URL sin el texto (para actualizarla en el navegador si se edita)
    principal: bool = False


class Canal(ABC):
    clave: str
    nombre: str
    icono: str
    envia_solo = False

    @abstractmethod
    def disponible(self, cliente) -> bool: ...

    @abstractmethod
    def accion(self, cliente, texto: str, principal: bool = False) -> AccionEnvio: ...

    def enviar(self, mensaje) -> None:  # pragma: no cover - para canales automáticos futuros
        raise NotImplementedError(_("Este canal no envía automáticamente."))


def _digitos(telefono: str) -> str:
    return "".join(c for c in telefono or "" if c.isdigit())


class WhatsAppEnlace(Canal):
    clave = CanalChoices.WHATSAPP
    nombre = "WhatsApp"
    icono = "whatsapp"

    def disponible(self, cliente) -> bool:
        return bool(_digitos(cliente.telefono))

    def accion(self, cliente, texto, principal=False):
        base = f"https://wa.me/{_digitos(cliente.telefono)}?text="
        return AccionEnvio(self.clave, self.nombre, self.icono, base + quote(texto, safe=""), base, principal)


class SMSEnlace(Canal):
    """`sms:` abre la app de mensajes del móvil, que usa RCS si está disponible."""

    clave = CanalChoices.SMS
    nombre = _("SMS / RCS")
    icono = "sms"

    def disponible(self, cliente) -> bool:
        return bool(_digitos(cliente.telefono))

    def accion(self, cliente, texto, principal=False):
        # «?&body=» funciona tanto en iOS como en Android
        base = f"sms:+{_digitos(cliente.telefono)}?&body="
        return AccionEnvio(self.clave, self.nombre, self.icono, base + quote(texto, safe=""), base, principal)


class Copia(Canal):
    clave = CanalChoices.COPIA
    nombre = _("Copiar")
    icono = "copiar"

    def disponible(self, cliente) -> bool:
        return True

    def accion(self, cliente, texto, principal=False):
        return AccionEnvio(self.clave, self.nombre, self.icono, None, None, principal)


REGISTRO: dict[str, Canal] = {c.clave: c for c in (WhatsAppEnlace(), SMSEnlace(), Copia())}
PREFERENCIA = {"whatsapp": CanalChoices.WHATSAPP, "sms": CanalChoices.SMS}


def obtener(clave: str) -> Canal | None:
    return REGISTRO.get(clave)


def canal_preferido(cliente) -> str:
    preferido = PREFERENCIA.get(cliente.canal_preferido, CanalChoices.WHATSAPP)
    canal = REGISTRO[preferido]
    return preferido if canal.disponible(cliente) else CanalChoices.COPIA


def acciones_para(cliente, texto: str) -> list[AccionEnvio]:
    """Botones de envío en orden: el preferido del cliente primero."""
    preferido = canal_preferido(cliente)
    orden = [preferido] + [c for c in REGISTRO if c != preferido]
    return [
        REGISTRO[c].accion(cliente, texto, principal=(c == preferido)) for c in orden if REGISTRO[c].disponible(cliente)
    ]
