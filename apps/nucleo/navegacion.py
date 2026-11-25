"""Menú de navegación e insignias de pendientes.

Los elementos cuya URL aún no existe se omiten, así que el menú se adapta a
las apps instaladas.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

ITEMS = [
    {
        "url": "panel:inicio",
        "etiqueta": _("Hoy"),
        "icono": "panel",
        "espacios": ["panel"],
        "atajo": "inicio",
        "movil": True,
    },
    {
        "url": "agenda:calendario",
        "etiqueta": _("Agenda"),
        "icono": "agenda",
        "espacios": ["agenda"],
        "atajo": "agenda",
        "movil": True,
    },
    {
        "url": "mensajeria:bandeja",
        "etiqueta": _("Mensajes"),
        "icono": "mensajes",
        "espacios": ["mensajeria"],
        "insignia": "mensajes",
        "atajo": "mensajes",
        "movil": True,
    },
    {"url": "clientes:lista", "etiqueta": _("Clientes"), "icono": "clientes", "espacios": ["clientes"], "movil": True},
    {
        "url": "solicitudes:lista",
        "etiqueta": _("Solicitudes"),
        "icono": "bandeja",
        "espacios": ["solicitudes"],
        "insignia": "solicitudes",
    },
    {"url": "catalogo:lista", "etiqueta": _("Flash"), "icono": "flash", "espacios": ["catalogo"]},
    {
        "url": "finanzas:resumen",
        "etiqueta": _("Finanzas"),
        "icono": "dinero",
        "espacios": ["finanzas"],
        "propietaria": True,
    },
    {"url": "ia:asistente", "etiqueta": _("Asistente IA"), "icono": "ia", "espacios": ["ia"]},
    {
        "url": "nucleo:ajustes",
        "etiqueta": _("Ajustes"),
        "icono": "ajustes",
        "espacios": ["nucleo"],
        "propietaria": True,
    },
]


def _url(nombre: str) -> str | None:
    try:
        return reverse(nombre)
    except NoReverseMatch:
        return None


def _contar(request) -> dict:
    cuentas = {"mensajes": 0, "solicitudes": 0}
    try:
        from apps.mensajeria.servicios import contar_pendientes_hoy

        cuentas["mensajes"] = contar_pendientes_hoy()
    except ImportError:
        pass
    try:
        from apps.agenda.models import SolicitudReserva

        cuentas["solicitudes"] = SolicitudReserva.objects.filter(estado=SolicitudReserva.Estado.NUEVA).count()
    except ImportError:
        pass
    return cuentas


def contadores(request) -> dict:
    cuentas = _contar(request)
    es_propietaria = getattr(request.user, "es_propietaria", False)
    match = getattr(request, "resolver_match", None)
    actual = match.namespace if match else ""
    items = []
    for item in ITEMS:
        if item.get("propietaria") and not es_propietaria:
            continue
        href = _url(item["url"])
        if not href:
            continue
        items.append(
            {
                **item,
                "href": href,
                "activo": actual in item["espacios"],
                "cuenta": cuentas.get(item.get("insignia", ""), 0),
            }
        )
    movil = [i for i in items if i.get("movil")]
    return {
        **cuentas,
        "items": items,
        "movil": movil,
        "resto": [i for i in items if not i.get("movil")],
        "url_nueva_cita": _url("agenda:nueva"),
        "url_nuevo_cliente": _url("clientes:nuevo"),
        "url_buscar": _url("clientes:lista"),
    }
