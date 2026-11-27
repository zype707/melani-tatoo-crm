"""Importación de clientes por lotes desde un CSV (Excel, Google Sheets, Numbers u otro CRM).

Flujo en tres pasos, sin tocar la base de datos hasta el último:

1. ``leer(contenido)``: decodifica el archivo (UTF-8, con o sin BOM, o Windows-1252/Latin-1 de Excel).
2. ``analizar(texto, formato_fecha=...)``: detecta el separador y las columnas (acepta nombres en
   español y en inglés), valida cada fila y la clasifica en nueva / ya existe / con error.
3. ``importar(analisis, ...)``: crea las fichas en una sola transacción.

El análisis es determinista: la vista guarda el texto en la sesión y lo vuelve a analizar al
confirmar, así la comprobación de duplicados se hace contra la base de datos de ese momento.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import Cliente, Etiqueta, EventoConsentimiento, OrigenConsentimiento
from .servicios import normalizar_telefono

LIMITE_BYTES = 2 * 1024 * 1024
LIMITE_FILAS = 5000
MAX_ETIQUETAS_FILA = 10

# Campos que se pueden importar, en el orden en que se explican y salen en la plantilla.
# Cada campo acepta varios nombres de columna (se comparan sin tildes, mayúsculas ni signos).
ALIAS = {
    "nombre": ("nombre", "nombres", "name", "first_name", "firstname", "first", "given_name", "primer_nombre"),
    "apellidos": (
        "apellidos",
        "apellido",
        "apellido_s",
        "last_name",
        "lastname",
        "last",
        "surname",
        "surnames",
        "family_name",
    ),
    "nombre_completo": (
        "nombre_completo",
        "nombre_y_apellidos",
        "full_name",
        "fullname",
        "cliente",
        "clienta",
        "client",
        "customer",
        "contacto",
        "contact",
    ),
    "telefono": (
        "telefono",
        "tel",
        "telefono_movil",
        "movil",
        "celular",
        "cel",
        "phone",
        "phone_number",
        "mobile",
        "mobile_phone",
        "cell",
        "cell_phone",
        "whatsapp",
    ),
    "email": ("email", "e_mail", "correo", "correo_electronico", "mail", "email_address"),
    "instagram": ("instagram", "ig", "insta", "usuario_instagram", "instagram_handle"),
    "fecha_nacimiento": (
        "fecha_nacimiento",
        "fecha_de_nacimiento",
        "nacimiento",
        "cumpleanos",
        "cumple",
        "birthday",
        "birthdate",
        "birth_date",
        "date_of_birth",
        "dob",
    ),
    "canal_preferido": ("canal_preferido", "canal", "preferred_channel", "channel"),
    "origen": ("origen", "como_llego", "source", "fuente", "referral_source"),
    "etiquetas": ("etiquetas", "etiqueta", "tags", "tag", "grupos", "grupo", "labels"),
    "notas": ("notas", "nota", "notes", "note", "comentarios", "observaciones", "comments"),
    "acepta_promociones": (
        "acepta_promociones",
        "promociones",
        "marketing",
        "acepta_marketing",
        "accepts_promotions",
        "accepts_marketing",
        "promotions",
        "newsletter",
        "opt_in",
        "optin",
    ),
    "no_contactar": ("no_contactar", "do_not_contact", "no_contact", "bloqueado", "no_molestar"),
    "cliente_desde": (
        "cliente_desde",
        "clienta_desde",
        "fecha_alta",
        "alta",
        "customer_since",
        "client_since",
        "created",
        "created_at",
        "desde",
        "primera_visita",
        "first_visit",
    ),
}

# Nombre de columna de la plantilla descargable en cada idioma de la interfaz.
CABECERAS_PLANTILLA = {
    "es": {
        "nombre": "nombre",
        "apellidos": "apellidos",
        "telefono": "telefono",
        "email": "email",
        "instagram": "instagram",
        "fecha_nacimiento": "fecha_nacimiento",
        "canal_preferido": "canal_preferido",
        "origen": "origen",
        "etiquetas": "etiquetas",
        "notas": "notas",
        "acepta_promociones": "acepta_promociones",
        "no_contactar": "no_contactar",
        "cliente_desde": "cliente_desde",
    },
    "en": {
        "nombre": "first_name",
        "apellidos": "last_name",
        "telefono": "phone",
        "email": "email",
        "instagram": "instagram",
        "fecha_nacimiento": "birthday",
        "canal_preferido": "preferred_channel",
        "origen": "source",
        "etiquetas": "tags",
        "notas": "notes",
        "acepta_promociones": "accepts_promotions",
        "no_contactar": "do_not_contact",
        "cliente_desde": "customer_since",
    },
}

# Explicación de cada columna para la página de importación (misma clave que ALIAS).
DESCRIPCION_COLUMNAS = [
    ("nombre", True, gettext_lazy("Nombre de pila. Obligatorio (o usa una columna «nombre_completo»).")),
    ("apellidos", False, gettext_lazy("Apellidos.")),
    (
        "nombre_completo",
        False,
        gettext_lazy("Solo si no tienes nombre y apellidos por separado: «Ana López» o «López, Ana»."),
    ),
    (
        "telefono",
        False,
        gettext_lazy("Con o sin formato: (407) 555-0123. Si no es de EE. UU., con prefijo: +34 612 345 678."),
    ),
    ("email", False, gettext_lazy("Correo electrónico.")),
    ("instagram", False, gettext_lazy("Usuario, con o sin @, o el enlace a su perfil.")),
    ("fecha_nacimiento", False, gettext_lazy("Para felicitarla. AAAA-MM-DD o el formato que elijas abajo.")),
    ("canal_preferido", False, gettext_lazy("«whatsapp» o «sms». Vacío = WhatsApp.")),
    (
        "origen",
        False,
        gettext_lazy("Cómo llegó: instagram, recomendacion, web, estudio, evento u otro."),
    ),
    ("etiquetas", False, gettext_lazy("Varias separadas por comas: «VIP, proyecto grande». Se crean solas.")),
    ("notas", False, gettext_lazy("Notas privadas: solo las ves tú.")),
    (
        "acepta_promociones",
        False,
        gettext_lazy("«sí» o «no». Si hay algún «sí», te preguntaremos cómo lo aceptaron (queda registrado)."),
    ),
    ("no_contactar", False, gettext_lazy("«sí» si pidió que no le escribas nunca (ni recordatorios).")),
    (
        "cliente_desde",
        False,
        gettext_lazy("Fecha de su primera visita. Así no cuentan como «nuevos del mes» y conservas su antigüedad."),
    ),
]

SI = {"si", "s", "yes", "y", "true", "1", "x", "verdadero", "acepta", "ok", "v"}
NO = {"no", "n", "false", "0", "falso", "no_acepta", "none", "nunca"}
CANALES = {
    Cliente.Canal.WHATSAPP: {"whatsapp", "wa", "whats", "wapp", "w"},
    Cliente.Canal.SMS: {"sms", "texto", "text", "rcs", "imessage", "mensaje", "sms_rcs", "mensaje_de_texto"},
}
ORIGENES_EXTRA = {
    Cliente.Origen.INSTAGRAM: {"ig", "insta"},
    Cliente.Origen.RECOMENDACION: {
        "recomendacion",
        "referido",
        "referida",
        "referral",
        "amigo",
        "amiga",
        "friend",
        "boca_a_boca",
        "word_of_mouth",
    },
    Cliente.Origen.WEB: {"web", "formulario", "formulario_web", "website", "pagina_web", "online", "google"},
    Cliente.Origen.ESTUDIO: {"estudio", "walk_in", "walkin", "local", "tienda", "studio"},
    Cliente.Origen.EVENTO: {"evento", "convencion", "convention", "event", "feria", "expo"},
    Cliente.Origen.OTRO: {"otro", "otra", "other"},
}


class ArchivoInvalido(Exception):
    """Problema con el archivo entero (no con una fila concreta)."""


@dataclass
class Fila:
    numero: int  # línea del archivo (la cabecera es la 1)
    original: dict
    datos: dict = field(default_factory=dict)
    errores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    existente_id: int | None = None
    existente_nombre: str = ""

    @property
    def estado(self) -> str:
        if self.errores:
            return "error"
        return "existe" if self.existente_id else "nueva"

    @property
    def nombre_completo(self) -> str:
        return f"{self.datos.get('nombre', '')} {self.datos.get('apellidos', '')}".strip()


@dataclass
class Analisis:
    columnas: list
    mapa: dict  # columna original → campo
    filas: list
    delimitador: str

    @property
    def ignoradas(self) -> list:
        return [c for c in self.columnas if c not in self.mapa]

    @property
    def campos(self) -> set:
        return set(self.mapa.values())

    @property
    def nuevas(self) -> list:
        return [f for f in self.filas if f.estado == "nueva"]

    @property
    def existentes(self) -> list:
        return [f for f in self.filas if f.estado == "existe"]

    @property
    def con_error(self) -> list:
        return [f for f in self.filas if f.estado == "error"]

    @property
    def con_avisos(self) -> list:
        return [f for f in self.filas if f.avisos and not f.errores]

    @property
    def con_promociones(self) -> int:
        return sum(1 for f in self.filas if not f.errores and f.datos.get("acepta_promociones"))


# --- Lectura ---------------------------------------------------------------------------------


def leer(contenido: bytes) -> str:
    """Bytes del archivo → texto. Prueba UTF-8 (con o sin BOM) y si no, Windows-1252 (Excel)."""
    if not contenido or not contenido.strip():
        raise ArchivoInvalido(_("El archivo está vacío."))
    if len(contenido) > LIMITE_BYTES:
        raise ArchivoInvalido(
            _("El archivo pesa más de %(mb)s MB. Divídelo en varios archivos más pequeños.")
            % {"mb": LIMITE_BYTES // (1024 * 1024)}
        )
    if contenido[:4] == b"PK\x03\x04" or contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ArchivoInvalido(
            _("Parece un archivo de Excel. Ábrelo y usa «Guardar como» → «CSV UTF-8 (delimitado por comas)».")
        )
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def clave(texto: str) -> str:
    """«Teléfono Móvil» → «telefono_movil» (para comparar cabeceras y valores sin manías)."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


_CAMPO_POR_ALIAS = {alias: campo for campo, aliases in ALIAS.items() for alias in aliases}


def _delimitador(texto: str) -> str:
    muestra = "\n".join(texto.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        primera = texto.splitlines()[0] if texto.splitlines() else ""
        return max(",;\t|", key=primera.count)


# --- Valores -----------------------------------------------------------------------------------


def _bool(texto: str) -> bool | None:
    t = clave(texto)
    if t in SI:
        return True
    if not t or t in NO:
        return False
    return None


def _anio(texto: str) -> int:
    anio = int(texto)
    if len(texto) == 2:
        corte = timezone.localdate().year % 100
        anio += 1900 if anio > corte else 2000
    return anio


def _fecha(texto: str, formato: str) -> date | None:
    """ISO (AAAA-MM-DD) siempre; DD/MM/AAAA o MM/DD/AAAA según `formato` ("dmy" o "mdy")."""
    t = (texto or "").strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T].*)?", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?:[ T].*)?", t)
    if not m:
        raise ValueError(t)
    a, b, anio = int(m.group(1)), int(m.group(2)), _anio(m.group(3))
    dia, mes = (a, b) if formato == "dmy" else (b, a)
    if mes > 12 >= dia:  # el otro formato es el único posible: no hay duda
        dia, mes = mes, dia
    return date(anio, mes, dia)


def _instagram(texto: str) -> str:
    t = (texto or "").strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", t)
    if m:
        t = m.group(1)
    return t.lstrip("@").strip().strip("/")


def _telefono(texto: str) -> str:
    t = (texto or "").strip()
    if re.fullmatch(r"\d+\.0", t):  # Excel convierte a veces el número en decimal
        t = t[:-2]
    return normalizar_telefono(t)


def _origenes() -> dict:
    """Valor del CSV (normalizado) → clave de Cliente.Origen. Admite las etiquetas en es y en."""
    mapa = {}
    for valor, aliases in ORIGENES_EXTRA.items():
        for a in aliases:
            mapa[a] = valor
    for idioma in ("es", "en"):
        with translation.override(idioma):
            for valor, etiqueta in Cliente.Origen.choices:
                mapa[clave(etiqueta)] = valor
                mapa[clave(valor)] = valor
    return mapa


def _canal(texto: str) -> str | None:
    t = clave(texto)
    if not t:
        return Cliente.Canal.WHATSAPP
    for canal, aliases in CANALES.items():
        if t in aliases:
            return canal
    return None


def _etiquetas(texto: str) -> list[str]:
    vistas, lista = set(), []
    for trozo in re.split(r"[,;|]", texto or ""):
        nombre = " ".join(trozo.split())[:40]
        if nombre and nombre.lower() not in vistas:
            vistas.add(nombre.lower())
            lista.append(nombre)
    return lista[:MAX_ETIQUETAS_FILA]


def _largo(fila: Fila, valor: str, maximo: int, nombre) -> str:
    if len(valor) > maximo:
        fila.errores.append(
            _("%(campo)s es demasiado largo (máx. %(max)s caracteres).") % {"campo": nombre, "max": maximo}
        )
    return valor


# --- Análisis ------------------------------------------------------------------------------------


def analizar(texto: str, *, formato_fecha: str = "mdy") -> Analisis:
    """Valida el CSV entero sin escribir nada. Lanza ArchivoInvalido si no se puede usar."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas_utiles = [linea for linea in texto.split("\n") if linea.strip()]
    if not lineas_utiles:
        raise ArchivoInvalido(_("El archivo está vacío."))
    delimitador = _delimitador(texto)
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    try:
        cabecera = next(lector)
    except (StopIteration, csv.Error) as exc:
        raise ArchivoInvalido(_("No se pudo leer el archivo como CSV.")) from exc

    columnas = [c.strip() for c in cabecera]
    mapa = {}
    for c in columnas:
        campo = _CAMPO_POR_ALIAS.get(clave(c))
        if campo and campo not in mapa.values():
            mapa[c] = campo
    campos = set(mapa.values())
    if "nombre" not in campos and "nombre_completo" not in campos:
        raise ArchivoInvalido(
            _(
                "No encuentro la columna del nombre. La primera fila debe tener los títulos de las columnas, "
                "por ejemplo: nombre, apellidos, telefono, email. Descarga la plantilla para ver un ejemplo."
            )
        )

    origenes = _origenes()
    por_telefono = dict(Cliente.objects.activos().exclude(telefono="").values_list("telefono", "pk"))
    por_email = {e.lower(): pk for e, pk in Cliente.objects.activos().exclude(email="").values_list("email", "pk")}
    vistos_tel, vistos_email = {}, {}
    filas = []
    hoy = timezone.localdate()
    try:
        for valores in lector:
            if not any(v.strip() for v in valores):
                continue
            if len(filas) >= LIMITE_FILAS:
                raise ArchivoInvalido(
                    _("El archivo tiene más de %(n)s clientes. Divídelo en varios archivos.") % {"n": LIMITE_FILAS}
                )
            original = {col: (valores[i].strip() if i < len(valores) else "") for i, col in enumerate(columnas)}
            fila = Fila(numero=lector.line_num, original=original)
            crudo = {campo: original.get(col, "") for col, campo in mapa.items()}
            _limpiar(fila, crudo, formato_fecha, origenes, hoy)
            if not fila.errores:
                _duplicados(fila, vistos_tel, vistos_email, por_telefono, por_email)
            filas.append(fila)
    except csv.Error as exc:
        raise ArchivoInvalido(_("El CSV está mal formado cerca de la línea %(n)s.") % {"n": lector.line_num}) from exc

    if not filas:
        raise ArchivoInvalido(_("El archivo solo tiene la fila de títulos: no hay clientes que importar."))
    ids = {f.existente_id for f in filas if f.existente_id}
    nombres = {c.pk: c.nombre_completo for c in Cliente.objects.filter(pk__in=ids)}
    for f in filas:
        if f.existente_id:
            f.existente_nombre = nombres.get(f.existente_id, "")
    return Analisis(columnas=columnas, mapa=mapa, filas=filas, delimitador=delimitador)


def _limpiar(fila: Fila, crudo: dict, formato_fecha: str, origenes: dict, hoy: date) -> None:
    d = fila.datos
    nombre = " ".join(crudo.get("nombre", "").split())
    apellidos = " ".join(crudo.get("apellidos", "").split())
    completo = crudo.get("nombre_completo", "").strip()
    if not nombre and completo:
        if "," in completo:  # «López García, Ana»
            apellidos_c, _coma, nombre_c = completo.partition(",")
            nombre, apellidos = " ".join(nombre_c.split()), apellidos or " ".join(apellidos_c.split())
        else:
            partes = completo.split()
            nombre, apellidos = partes[0], apellidos or " ".join(partes[1:])
    if not nombre:
        fila.errores.append(_("Falta el nombre."))
    d["nombre"] = _largo(fila, nombre, 80, _("El nombre"))
    d["apellidos"] = _largo(fila, apellidos, 120, _("Los apellidos"))

    d["telefono"] = ""
    telefono_invalido = False
    if crudo.get("telefono", "").strip():
        try:
            d["telefono"] = _telefono(crudo["telefono"])
        except ValidationError as exc:
            telefono_invalido = True
            fila.errores.append(f"{exc.messages[0]} ({crudo['telefono'].strip()})")

    d["email"] = crudo.get("email", "").strip()
    if d["email"]:
        try:
            validate_email(d["email"])
        except ValidationError:
            fila.errores.append(_("El email «%(email)s» no es válido.") % {"email": d["email"]})
        _largo(fila, d["email"], 254, _("El email"))

    d["instagram"] = _largo(fila, _instagram(crudo.get("instagram", "")), 60, "Instagram")

    if not (d["telefono"] or d["email"] or d["instagram"] or telefono_invalido):
        fila.errores.append(_("Falta un dato de contacto: teléfono, email o Instagram."))

    for campo, nombre_campo, minimo in (
        ("fecha_nacimiento", _("La fecha de nacimiento"), 1900),
        ("cliente_desde", _("La fecha «cliente desde»"), 1950),
    ):
        valor = crudo.get(campo, "")
        d[campo] = None
        try:
            fecha = _fecha(valor, formato_fecha)
        except ValueError:
            fila.errores.append(
                _("%(campo)s «%(valor)s» no se entiende. Usa AAAA-MM-DD, DD/MM/AAAA o MM/DD/AAAA.")
                % {"campo": nombre_campo, "valor": valor.strip()}
            )
            continue
        if fecha and (fecha > hoy or fecha.year < minimo):
            fila.errores.append(
                _("%(campo)s «%(valor)s» no es posible.") % {"campo": nombre_campo, "valor": valor.strip()}
            )
            continue
        d[campo] = fecha

    canal = _canal(crudo.get("canal_preferido", ""))
    if canal is None:
        fila.avisos.append(
            _("Canal «%(valor)s» desconocido: se usará WhatsApp.") % {"valor": crudo["canal_preferido"].strip()}
        )
        canal = Cliente.Canal.WHATSAPP
    d["canal_preferido"] = canal

    origen_txt = crudo.get("origen", "").strip()
    d["origen"] = origenes.get(clave(origen_txt), "") if origen_txt else ""
    if origen_txt and not d["origen"]:
        d["origen"] = Cliente.Origen.OTRO
        fila.avisos.append(_("Origen «%(valor)s» desconocido: se guardará como «Otro».") % {"valor": origen_txt})

    d["etiquetas"] = _etiquetas(crudo.get("etiquetas", ""))
    d["notas"] = crudo.get("notas", "").strip()[:5000]

    for campo, nombre_campo in (
        ("acepta_promociones", _("Acepta promociones")),
        ("no_contactar", _("No contactar")),
    ):
        valor = _bool(crudo.get(campo, ""))
        if valor is None:
            fila.avisos.append(
                _("«%(campo)s»: no entiendo «%(valor)s», se toma como «no».")
                % {"campo": nombre_campo, "valor": crudo[campo].strip()}
            )
            valor = False
        d[campo] = valor


def _duplicados(fila: Fila, vistos_tel, vistos_email, por_telefono, por_email) -> None:
    d = fila.datos
    email = d["email"].lower()
    previa = (d["telefono"] and vistos_tel.get(d["telefono"])) or (email and vistos_email.get(email))
    if previa:
        fila.errores.append(
            _("Repite el teléfono o el email de la fila %(n)s (¿es la misma persona?).") % {"n": previa}
        )
        return
    if d["telefono"]:
        vistos_tel[d["telefono"]] = fila.numero
    if email:
        vistos_email[email] = fila.numero
    fila.existente_id = (d["telefono"] and por_telefono.get(d["telefono"])) or (email and por_email.get(email)) or None


# --- Importación -----------------------------------------------------------------------------------


def _momento(dia: date | None):
    if not dia:
        return timezone.now()
    return timezone.make_aware(datetime.combine(dia, time(12)))


def _etiquetas_por_nombre(nombres: set[str]) -> dict:
    """Devuelve {nombre_en_minúsculas: Etiqueta}, creando las que falten."""
    if not nombres:
        return {}
    existentes = {e.nombre.lower(): e for e in Etiqueta.objects.all()}
    nuevas = {}
    for n in nombres:
        if n.lower() not in existentes and n.lower() not in nuevas:
            nuevas[n.lower()] = Etiqueta(nombre=n)
    Etiqueta.objects.bulk_create(nuevas.values(), ignore_conflicts=True)
    return {e.nombre.lower(): e for e in Etiqueta.objects.all()}


@transaction.atomic
def importar(
    analisis: Analisis,
    *,
    si_existe: str = "omitir",
    origen_consentimiento: str = "",
    etiqueta_lote: str = "",
    usuario=None,
) -> dict:
    """Crea las fichas nuevas (y completa las existentes si se pide). Todo o nada."""
    validos = {v for v, _x in OrigenConsentimiento.choices if v != OrigenConsentimiento.PETICION_BAJA}
    origen = origen_consentimiento if origen_consentimiento in validos else ""
    ahora = timezone.now()
    nota_evento = _("Importado desde CSV")
    lote = " ".join((etiqueta_lote or "").split())[:40]

    nuevas = analisis.nuevas
    existentes = analisis.existentes if si_existe == "completar" else []
    nombres = {n for f in [*nuevas, *existentes] for n in f.datos["etiquetas"]}
    if lote and (nuevas or existentes):
        nombres.add(lote)
    etiquetas = _etiquetas_por_nombre(nombres)

    clientes = []
    for f in nuevas:
        d = f.datos
        acepta = bool(origen and d["acepta_promociones"])
        clientes.append(
            Cliente(
                nombre=d["nombre"],
                apellidos=d["apellidos"],
                telefono=d["telefono"],
                email=d["email"],
                instagram=d["instagram"],
                fecha_nacimiento=d["fecha_nacimiento"],
                canal_preferido=d["canal_preferido"],
                origen=d["origen"],
                notas=d["notas"],
                contacto_bloqueado=d["no_contactar"],
                marketing_consentimiento=acepta,
                marketing_fecha=ahora if acepta else None,
                marketing_origen=origen if acepta else "",
                creado_en=_momento(d["cliente_desde"]),
            )
        )
    Cliente.objects.bulk_create(clientes, batch_size=500)

    Relacion = Cliente.etiquetas.through
    relaciones, eventos = [], []
    for c, f in zip(clientes, nuevas, strict=True):
        for n in [*f.datos["etiquetas"], *([lote] if lote else [])]:
            relaciones.append(Relacion(cliente_id=c.pk, etiqueta_id=etiquetas[n.lower()].pk))
        if c.marketing_consentimiento:
            eventos.append(
                EventoConsentimiento(
                    cliente=c,
                    tipo=EventoConsentimiento.Tipo.ALTA,
                    origen=origen,
                    usuario=usuario,
                    notas=nota_evento,
                )
            )

    completados = 0
    consentimientos = len(eventos)
    for f in existentes:
        cliente = Cliente.objects.select_for_update().get(pk=f.existente_id)
        cambios = _completar(cliente, f.datos)
        if f.datos["acepta_promociones"] and origen and not cliente.marketing_consentimiento:
            cliente.dar_consentimiento(origen, usuario, nota_evento)
            consentimientos += 1
            cambios = True
        for n in [*f.datos["etiquetas"], *([lote] if lote else [])]:
            relaciones.append(Relacion(cliente_id=cliente.pk, etiqueta_id=etiquetas[n.lower()].pk))
        completados += bool(cambios or f.datos["etiquetas"] or lote)

    Relacion.objects.bulk_create(relaciones, ignore_conflicts=True)
    EventoConsentimiento.objects.bulk_create(eventos)
    return {
        "creados": len(clientes),
        "completados": completados,
        "omitidos": len(analisis.existentes) - len(existentes),
        "errores": len(analisis.con_error),
        "consentimientos": consentimientos,
    }


def _completar(cliente: Cliente, d: dict) -> bool:
    """Rellena solo lo que la ficha tiene vacío. Nunca sobrescribe datos que ya existen."""
    campos = []
    for campo in ("apellidos", "telefono", "email", "instagram", "fecha_nacimiento", "origen", "notas"):
        if d.get(campo) and not getattr(cliente, campo):
            setattr(cliente, campo, d[campo])
            campos.append(campo)
    if d.get("no_contactar") and not cliente.contacto_bloqueado:
        cliente.contacto_bloqueado = True
        campos.append("contacto_bloqueado")
    if campos:
        cliente.save(update_fields=[*campos, "actualizado_en"])
    return bool(campos)


# --- Archivos descargables ------------------------------------------------------------------------


def _csv(filas: list[list]) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\r\n")
    for fila in filas:
        escritor.writerow([_sin_formula(v) for v in fila])
    return "﻿" + salida.getvalue()  # BOM: Excel abre bien las tildes


def _sin_formula(valor) -> str:
    """Evita que Excel interprete un valor como fórmula al abrir el CSV."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") and not re.fullmatch(r"[+\-]?[\d ().-]+", texto) else texto


def plantilla_csv(idioma: str | None = None) -> str:
    """CSV de ejemplo con todas las columnas y dos clientes ficticios."""
    idioma = "en" if (idioma or settings.LANGUAGE_CODE).startswith("en") else "es"
    cab = CABECERAS_PLANTILLA[idioma]
    ejemplos = {
        "es": [
            [
                "Ana",
                "López García",
                "(407) 555-0123",
                "ana@ejemplo.com",
                "@ana.tattoo",
                "1994-03-21",
                "whatsapp",
                "instagram",
                "VIP, fine line",
                "Alérgica al látex",
                "sí",
                "no",
                "2023-06-10",
            ],
            ["Bruno", "Díaz", "+34 612 345 678", "", "", "", "sms", "recomendacion", "", "", "no", "no", ""],
        ],
        "en": [
            [
                "Ana",
                "Lopez",
                "(407) 555-0123",
                "ana@example.com",
                "@ana.tattoo",
                "1994-03-21",
                "whatsapp",
                "instagram",
                "VIP, fine line",
                "Latex allergy",
                "yes",
                "no",
                "2023-06-10",
            ],
            ["Bruno", "Diaz", "+34 612 345 678", "", "", "", "sms", "referral", "", "", "no", "no", ""],
        ],
    }[idioma]
    orden = list(cab)
    return _csv([[cab[c] for c in orden], *ejemplos])


def csv_errores(analisis: Analisis) -> str:
    """Las filas que no se importan, con sus columnas originales y el motivo, para corregir y reintentar."""
    titulo_motivo = _("motivo")
    filas = [[*analisis.columnas, titulo_motivo]]
    for f in analisis.con_error:
        filas.append([*(f.original.get(c, "") for c in analisis.columnas), " · ".join(f.errores)])
    return _csv(filas)
