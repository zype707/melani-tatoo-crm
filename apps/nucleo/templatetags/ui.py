"""Etiquetas y filtros de interfaz (cargados como builtins en todas las plantillas)."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import phonenumbers
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils import timezone
from django.utils.dateformat import format as dformat
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def icono(nombre: str, clase: str = "", etiqueta: str = ""):
    """Icono del sprite SVG propio. Con `etiqueta` se anuncia a lectores de pantalla."""
    if etiqueta:
        return format_html(
            '<svg class="icono {}" role="img" aria-label="{}"><use href="{}#i-{}"></use></svg>',
            clase,
            etiqueta,
            static("img/iconos.svg"),
            nombre,
        )
    return format_html(
        '<svg class="icono {}" aria-hidden="true" focusable="false"><use href="{}#i-{}"></use></svg>',
        clase,
        static("img/iconos.svg"),
        nombre,
    )


@register.simple_tag(takes_context=True)
def nav_activo(context, *espacios):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    if match and match.namespace in espacios:
        return mark_safe('aria-current="page"')
    return ""


# --- Dinero y números ---------------------------------------------------------


def _decimal(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def dinero(valor, decimales="auto"):
    d = _decimal(valor)
    if d is None:
        return "—"
    negativo = d < 0
    d = abs(d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if decimales == "auto" and d == d.to_integral_value():
        texto = f"{int(d):,}"
    else:
        texto = f"{d:,.2f}"
    return f"{'−' if negativo else ''}{settings.SIMBOLO_MONEDA}{texto}"


@register.filter
def porcentaje(valor, decimales=0):
    if valor is None:
        return "—"
    try:
        return f"{float(valor) * 100:.{int(decimales)}f} %"
    except (TypeError, ValueError):
        return "—"


# --- Fechas -------------------------------------------------------------------


def _local(valor):
    if isinstance(valor, datetime):
        return timezone.localtime(valor) if timezone.is_aware(valor) else valor
    return valor


@register.filter
def hora(valor):
    valor = _local(valor)
    if not valor:
        return ""
    h = valor.hour % 12 or 12
    return f"{h}:{valor.minute:02d} {'am' if valor.hour < 12 else 'pm'}"


@register.filter
def fecha_corta(valor):
    """«jue 27 nov» (añade el año si no es el actual)."""
    valor = _local(valor)
    if not valor:
        return ""
    texto = dformat(valor, "D j M")
    if valor.year != timezone.localdate().year:
        texto += f" {valor.year}"
    return texto


@register.filter
def fecha_larga(valor):
    """«jueves 27 de noviembre» (con año si no es el actual)."""
    valor = _local(valor)
    if not valor:
        return ""
    texto = dformat(valor, r"l j \d\e F")
    if valor.year != timezone.localdate().year:
        texto += f" de {valor.year}"
    return texto


@register.filter
def fecha_numerica(valor):
    valor = _local(valor)
    return dformat(valor, "d/m/Y") if valor else ""


@register.filter
def relativo(valor):
    """«hoy», «mañana», «hace 3 días», «en 2 meses»."""
    valor = _local(valor)
    if not valor:
        return ""
    dia = valor.date() if isinstance(valor, datetime) else valor
    dias = (dia - timezone.localdate()).days
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    if dias == -1:
        return "ayer"
    n = abs(dias)
    if n < 30:
        cantidad = f"{n} días"
    elif n < 365:
        meses = round(n / 30.4)
        cantidad = "1 mes" if meses == 1 else f"{meses} meses"
    else:
        anios = n // 365
        cantidad = "1 año" if anios == 1 else f"{anios} años"
    return f"en {cantidad}" if dias > 0 else f"hace {cantidad}"


@register.filter
def edad(fecha_nacimiento):
    if not isinstance(fecha_nacimiento, date):
        return ""
    hoy = timezone.localdate()
    return hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))


@register.filter
def duracion(minutos):
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        return ""
    h, m = divmod(minutos, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


# --- Personas -------------------------------------------------------------------


@register.filter
def telefono(valor):
    if not valor:
        return ""
    try:
        numero = phonenumbers.parse(valor, settings.REGION_TELEFONO)
        region = phonenumbers.region_code_for_number(numero)
        formato = (
            phonenumbers.PhoneNumberFormat.NATIONAL
            if region == settings.REGION_TELEFONO
            else phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        return phonenumbers.format_number(numero, formato)
    except phonenumbers.NumberParseException:
        return valor


@register.filter
def iniciales(texto):
    partes = [p for p in str(texto or "").split() if p[:1].isalpha()]
    return ("".join(p[0] for p in partes[:2]) or "·").upper()


@register.filter
def obtener(diccionario, clave):
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None
