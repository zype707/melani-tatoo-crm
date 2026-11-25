"""Búsqueda en lenguaje natural.

La IA solo traduce la frase a un JSON de filtros con un esquema cerrado.
Aquí se valida cada valor contra listas permitidas y se construye la consulta
con el ORM. Nunca se ejecuta SQL ni código que venga de la IA.
"""

import re
import unicodedata
from datetime import timedelta

from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.utils.dates import MONTHS
from django.utils.translation import gettext as _

from apps.clientes.models import Cliente, Etiqueta, Tatuaje

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
ORDENES = ["nombre", "ultima_visita", "gasto", "reciente"]

ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "estilos",
        "zonas",
        "tamanos",
        "etiquetas",
        "estado_tatuaje",
        "sin_visita_meses",
        "visita_ultimos_meses",
        "cumple_mes",
        "gasto_minimo",
        "solo_promociones",
        "texto",
        "orden",
    ],
    "properties": {
        "estilos": {"type": "array", "items": {"type": "string", "enum": [v for v, _ in Tatuaje.Estilo.choices]}},
        "zonas": {"type": "array", "items": {"type": "string", "enum": [v for v, _ in Tatuaje.Zona.choices]}},
        "tamanos": {"type": "array", "items": {"type": "string", "enum": [v for v, _ in Tatuaje.Tamano.choices]}},
        "etiquetas": {"type": "array", "items": {"type": "string"}},
        "estado_tatuaje": {"type": ["string", "null"], "enum": ["en_proceso", "terminado", None]},
        "sin_visita_meses": {"type": ["integer", "null"]},
        "visita_ultimos_meses": {"type": ["integer", "null"]},
        "cumple_mes": {"type": ["integer", "null"]},
        "gasto_minimo": {"type": ["number", "null"]},
        "solo_promociones": {"type": ["boolean", "null"]},
        "texto": {
            "type": ["string", "null"],
            "description": "Nombre o palabra a buscar en nombre del cliente o título.",
        },
        "orden": {"type": "string", "enum": ORDENES},
    },
}

INSTRUCCIONES = (
    "Traduce la búsqueda de una tatuadora sobre sus clientes a filtros JSON. Valores de estilo, zona y tamaño: "
    "usa solo los del esquema (fine_line, blackwork, realismo… / brazo, antebrazo… / mini, pequeno, mediano, grande, xl). "
    "Si algo no se pide, deja la lista vacía o null. 'no vienen desde hace 6 meses' => sin_visita_meses=6. "
    "'han venido este año' => visita_ultimos_meses=12. 'cumplen en marzo' => cumple_mes=3. Orden por defecto: nombre."
)


def _plano(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def validar(filtros: dict) -> dict:
    """Limpia lo que devuelva la IA (o el intérprete local): solo valores conocidos."""
    estilos = {v for v, _ in Tatuaje.Estilo.choices}
    zonas = {v for v, _ in Tatuaje.Zona.choices}
    tamanos = {v for v, _ in Tatuaje.Tamano.choices}

    def entero(valor, minimo, maximo):
        try:
            v = int(valor)
            return v if minimo <= v <= maximo else None
        except (TypeError, ValueError):
            return None

    try:
        gasto = float(filtros.get("gasto_minimo")) if filtros.get("gasto_minimo") is not None else None
    except (TypeError, ValueError):
        gasto = None
    return {
        "estilos": [e for e in filtros.get("estilos") or [] if e in estilos][:6],
        "zonas": [z for z in filtros.get("zonas") or [] if z in zonas][:6],
        "tamanos": [t for t in filtros.get("tamanos") or [] if t in tamanos][:5],
        "etiquetas": [str(e)[:40] for e in filtros.get("etiquetas") or []][:5],
        "estado_tatuaje": filtros.get("estado_tatuaje")
        if filtros.get("estado_tatuaje") in ("en_proceso", "terminado")
        else None,
        "sin_visita_meses": entero(filtros.get("sin_visita_meses"), 1, 120),
        "visita_ultimos_meses": entero(filtros.get("visita_ultimos_meses"), 1, 120),
        "cumple_mes": entero(filtros.get("cumple_mes"), 1, 12),
        "gasto_minimo": gasto if gasto and 0 < gasto < 1_000_000 else None,
        "solo_promociones": filtros.get("solo_promociones")
        if isinstance(filtros.get("solo_promociones"), bool)
        else None,
        "texto": (str(filtros.get("texto") or "")[:60]).strip() or None,
        "orden": filtros.get("orden") if filtros.get("orden") in ORDENES else "nombre",
    }


def aplicar(filtros: dict):
    """Filtros validados → QuerySet de clientes (solo ORM)."""
    from apps.agenda.models import EstadoCita
    from apps.finanzas.models import Pago

    f = validar(filtros)
    qs = Cliente.objects.activos()
    tatuajes = Q()
    if f["estilos"]:
        tatuajes &= Q(tatuajes__estilo__in=f["estilos"])
    if f["zonas"]:
        tatuajes &= Q(tatuajes__zona__in=f["zonas"])
    if f["tamanos"]:
        tatuajes &= Q(tatuajes__tamano__in=f["tamanos"])
    if f["estado_tatuaje"]:
        tatuajes &= Q(tatuajes__estado=f["estado_tatuaje"])
    if tatuajes:
        qs = qs.filter(tatuajes)
    for nombre in f["etiquetas"]:
        qs = qs.filter(etiquetas__nombre__iexact=nombre)
    if f["cumple_mes"]:
        qs = qs.filter(fecha_nacimiento__month=f["cumple_mes"])
    if f["solo_promociones"]:
        qs = qs.filter(marketing_consentimiento=True, contacto_bloqueado=False)
    if f["texto"]:
        qs = qs.filter(
            Q(nombre__unaccent__icontains=f["texto"])
            | Q(apellidos__unaccent__icontains=f["texto"])
            | Q(tatuajes__titulo__unaccent__icontains=f["texto"])
        )
    qs = qs.annotate(ultima=Max("citas__inicio", filter=Q(citas__estado=EstadoCita.REALIZADA)))
    ahora = timezone.now()
    if f["sin_visita_meses"]:
        qs = qs.filter(ultima__lt=ahora - timedelta(days=round(30.44 * f["sin_visita_meses"])))
    if f["visita_ultimos_meses"]:
        qs = qs.filter(ultima__gte=ahora - timedelta(days=round(30.44 * f["visita_ultimos_meses"])))
    gasto = (
        Pago.objects.filter(cliente=OuterRef("pk"), devuelto=False)
        .values("cliente")
        .annotate(t=Sum("importe"))
        .values("t")[:1]
    )
    qs = qs.annotate(gasto=Subquery(gasto), n_tatuajes=Count("tatuajes", distinct=True))
    if f["gasto_minimo"]:
        qs = qs.filter(gasto__gte=f["gasto_minimo"])
    orden = {"ultima_visita": "-ultima", "gasto": "-gasto", "reciente": "-creado_en"}.get(f["orden"], "nombre")
    return qs.distinct().order_by(orden, "pk"), f


# --- Intérprete local (sin IA) -----------------------------------------------------------------

SINONIMOS_ESTILO = {
    "fine line": "fine_line",
    "fineline": "fine_line",
    "linea fina": "fine_line",
    "blackwork": "blackwork",
    "realis": "realismo",
    "tradicional": "tradicional",
    "old school": "tradicional",
    "neotrad": "neotradicional",
    "acuarela": "acuarela",
    "watercolor": "acuarela",
    "geometr": "geometrico",
    "letter": "lettering",
    "letras": "lettering",
    "minimal": "minimalista",
    "japon": "japones",
    "dotwork": "dotwork",
    "puntillismo": "dotwork",
}
SINONIMOS_ZONA = {
    "antebrazo": "antebrazo",
    "brazo": "brazo",
    "mano": "mano",
    "dedo": "mano",
    "hombro": "hombro",
    "espalda": "espalda",
    "pecho": "pecho",
    "costilla": "costillas",
    "abdomen": "abdomen",
    "cadera": "cadera",
    "muslo": "muslo",
    "pierna": "pierna",
    "gemelo": "pierna",
    "tobillo": "tobillo",
    "pie": "tobillo",
    "cuello": "cuello",
    "nuca": "cuello",
    "cara": "cara",
    "oreja": "oreja",
}


def interpretar_local(frase: str) -> dict:
    """Interpretación sencilla por palabras clave para cuando no hay IA."""
    t = _plano(frase)
    filtros = {"estilos": [], "zonas": [], "tamanos": [], "etiquetas": [], "orden": "nombre"}
    for clave, valor in SINONIMOS_ESTILO.items():
        if clave in t and valor not in filtros["estilos"]:
            filtros["estilos"].append(valor)
    for clave, valor in SINONIMOS_ZONA.items():
        if re.search(rf"\b{clave}", t) and valor not in filtros["zonas"]:
            if valor == "brazo" and "antebrazo" in t:
                continue
            filtros["zonas"].append(valor)
    if "vip" in t:
        filtros["etiquetas"].append("VIP")
    if m := re.search(r"(?:no (?:vienen|viene|han venido)|sin venir|sin visita)\D{0,20}(\d+)\s*mes", t):
        filtros["sin_visita_meses"] = int(m.group(1))
    if m := re.search(r"(?:este ano|ultimo ano)", t):
        filtros["visita_ultimos_meses"] = 12
    for i, mes in enumerate(MESES, start=1):
        if "cumple" in t and mes in t:
            filtros["cumple_mes"] = i
    if "a medias" in t or "en proceso" in t or "sin terminar" in t:
        filtros["estado_tatuaje"] = "en_proceso"
    if "promo" in t or "consentimiento" in t:
        filtros["solo_promociones"] = True
    if "gastado" in t or "gasto" in t or "mejores" in t:
        filtros["orden"] = "gasto"
    if m := re.search(r"(?:mas de|\+)\s*\$?\s*(\d{2,6})", t):
        filtros["gasto_minimo"] = int(m.group(1))
    _x = Etiqueta  # las etiquetas se validan al aplicar
    return filtros


def describir(f: dict) -> list[str]:
    partes = []
    if f["estilos"]:
        partes.append(_("Estilo: %(v)s") % {"v": ", ".join(str(Tatuaje.Estilo(e).label) for e in f["estilos"])})
    if f["zonas"]:
        partes.append(_("Zona: %(v)s") % {"v": ", ".join(str(Tatuaje.Zona(z).label) for z in f["zonas"])})
    if f["tamanos"]:
        partes.append(_("Tamaño: %(v)s") % {"v": ", ".join(str(Tatuaje.Tamano(t).label) for t in f["tamanos"])})
    if f["estado_tatuaje"]:
        partes.append(_("Tatuaje en proceso") if f["estado_tatuaje"] == "en_proceso" else _("Tatuaje terminado"))
    if f["etiquetas"]:
        partes.append(_("Etiqueta: %(v)s") % {"v": ", ".join(f["etiquetas"])})
    if f["sin_visita_meses"]:
        partes.append(_("Sin venir desde hace %(n)s+ meses") % {"n": f["sin_visita_meses"]})
    if f["visita_ultimos_meses"]:
        partes.append(_("Vino en los últimos %(n)s meses") % {"n": f["visita_ultimos_meses"]})
    if f["cumple_mes"]:
        partes.append(_("Cumple en %(mes)s") % {"mes": MONTHS[f["cumple_mes"]]})
    if f["gasto_minimo"]:
        partes.append(_("Gasto ≥ %(n).0f") % {"n": f["gasto_minimo"]})
    if f["solo_promociones"]:
        partes.append(_("Aceptan promociones"))
    if f["texto"]:
        partes.append(_("Texto: «%(t)s»") % {"t": f["texto"]})
    return partes
