"""Consentimiento informado: firma en canvas → PDF archivado en la ficha."""

import base64
import binascii
import hashlib
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.nucleo.imagenes import procesar_png_firma
from apps.nucleo.models import AjustesEstudio
from apps.nucleo.templatetags.ui import telefono as telefono_legible

from .models import ConsentimientoInformado, DatosSalud

MAX_FIRMA_BYTES = 600 * 1024
PREFIJO = "data:image/png;base64,"
ETIQUETAS_SALUD = {
    "alergias": gettext_lazy("Alergias"),
    "medicacion": gettext_lazy("Medicación"),
    "anticoagulantes": gettext_lazy("Anticoagulantes"),
    "diabetes": gettext_lazy("Diabetes"),
    "epilepsia": gettext_lazy("Epilepsia"),
    "problemas_cardiacos": gettext_lazy("Problemas cardíacos"),
    "embarazo_lactancia": gettext_lazy("Embarazo o lactancia"),
    "condiciones_piel": gettext_lazy("Condiciones de la piel"),
    "otras": gettext_lazy("Otras observaciones"),
}


def decodificar_firma(data_url: str) -> ContentFile:
    """Valida la firma enviada desde el canvas y la devuelve como PNG limpio."""
    if not data_url or not data_url.startswith(PREFIJO):
        raise ValidationError(_("Falta la firma."))
    try:
        datos = base64.b64decode(data_url[len(PREFIJO) :], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(_("La firma no es válida.")) from exc
    if len(datos) > MAX_FIRMA_BYTES:
        raise ValidationError(_("La firma es demasiado grande."))
    limpia = procesar_png_firma(datos)  # valida firma binaria, tamaño y re-codifica
    imagen = Image.open(BytesIO(limpia.read())).convert("L")
    limpia.seek(0)
    caja = imagen.point(lambda p: 255 if p < 200 else 0).getbbox()
    if not caja or (caja[2] - caja[0]) < 40 or (caja[3] - caja[1]) < 15:
        raise ValidationError(_("La firma está vacía o es demasiado pequeña. Firma con el dedo dentro del recuadro."))
    return limpia


def _pdf(c: ConsentimientoInformado, firma_bytes: bytes, ajustes: AjustesEstudio) -> bytes:
    # El PDF va en el idioma del contenido, el mismo del texto legal que se firma.
    with translation.override(settings.LANGUAGE_CODE):
        return _generar_pdf(c, firma_bytes, ajustes)


def _generar_pdf(c: ConsentimientoInformado, firma_bytes: bytes, ajustes: AjustesEstudio) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=_("Consentimiento · %(nombre)s") % {"nombre": c.nombre_firmante},
        author=ajustes.nombre,
    )
    base = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=0)
    sub = ParagraphStyle(
        "s", parent=base["Normal"], fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#444444")
    )
    cuerpo = ParagraphStyle("c", parent=base["Normal"], fontName="Helvetica", fontSize=10, leading=14)
    h2 = ParagraphStyle(
        "h", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4
    )

    p = escape
    elementos = [
        Paragraph(p(ajustes.nombre), titulo),
        Paragraph(p(" · ".join(filter(None, [ajustes.direccion, ajustes.telefono, ajustes.email]))), sub),
        Spacer(1, 6 * mm),
        Paragraph(_("Consentimiento informado para tatuaje"), h2),
    ]
    cliente = c.cliente
    filas = [
        [_("Cliente"), p(c.nombre_firmante)],
        [_("Fecha de nacimiento"), c.respuestas.get("fecha_nacimiento", "")],
        [_("Teléfono"), p(telefono_legible(cliente.telefono) or "—")],
        [_("Fecha y hora de la firma"), timezone.localtime(c.firmado_en).strftime(_("%d/%m/%Y %H:%M %Z"))],
        [_("Versión del texto"), str(c.version_texto)],
    ]
    if c.cita_id:
        filas.append([_("Cita"), timezone.localtime(c.cita.inicio).strftime(_("%d/%m/%Y %H:%M")) + f" · {c.cita.tipo}"])
    tabla = Table(filas, colWidths=[50 * mm, 120 * mm])
    tabla.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elementos += [tabla, Paragraph(_("Declaración de salud"), h2)]
    salud = c.respuestas.get("salud", {})
    filas_salud = []
    for clave, etiqueta in ETIQUETAS_SALUD.items():
        valor = salud.get(clave)
        if isinstance(valor, bool):
            valor = _("Sí") if valor else _("No")
        filas_salud.append([str(etiqueta), Paragraph(p(valor or "—"), cuerpo)])
    tabla_salud = Table(filas_salud, colWidths=[50 * mm, 120 * mm])
    tabla_salud.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
            ]
        )
    )
    elementos += [tabla_salud, Paragraph(_("Texto aceptado"), h2)]
    for parrafo in c.texto.split("\n"):
        if parrafo.strip():
            elementos.append(Paragraph(p(parrafo), cuerpo))
    elementos += [Paragraph(_("Autorizaciones"), h2)]
    for texto, valor in (
        (_("Fotos del tatuaje para el portfolio del estudio"), c.respuestas.get("autoriza_fotos")),
        (_("Recibir felicitaciones y novedades"), c.respuestas.get("acepta_marketing")),
    ):
        elementos.append(Paragraph(f"{p(texto)}: <b>{_('Sí') if valor else _('No')}</b>", cuerpo))
    elementos += [Spacer(1, 6 * mm), Paragraph(_("Firma"), h2)]
    firma = Image.open(BytesIO(firma_bytes))
    ancho = 70 * mm
    alto = ancho * firma.height / max(firma.width, 1)
    elementos.append(RLImage(BytesIO(firma_bytes), width=ancho, height=min(alto, 35 * mm), hAlign="LEFT"))
    elementos.append(Paragraph(p(c.nombre_firmante), sub))
    elementos.append(Spacer(1, 4 * mm))
    ip = f" · IP {c.ip}" if c.ip else ""
    elementos.append(
        Paragraph(_("Firmado digitalmente en el estudio%(ip)s. Documento n.º %(num)s.") % {"ip": ip, "num": c.pk}, sub)
    )
    doc.build(elementos)
    return buf.getvalue()


@transaction.atomic
def registrar(
    cliente,
    *,
    cita,
    nombre: str,
    fecha_nacimiento: date,
    salud: dict,
    firma_data_url: str,
    autoriza_fotos: bool,
    acepta_marketing: bool,
    ip: str | None,
    usuario=None,
) -> ConsentimientoInformado:
    ajustes = AjustesEstudio.obtener()
    firma = decodificar_firma(firma_data_url)
    firma_bytes = firma.read()
    firma.seek(0)

    DatosSalud.objects.update_or_create(cliente=cliente, defaults=salud)
    if not cliente.fecha_nacimiento:
        cliente.fecha_nacimiento = fecha_nacimiento
        cliente.save(update_fields=["fecha_nacimiento", "actualizado_en"])
    if acepta_marketing and not cliente.marketing_consentimiento:
        cliente.dar_consentimiento("presencial", usuario, "Casilla del consentimiento firmado")

    hoy = timezone.localdate()
    c = ConsentimientoInformado.objects.create(
        cliente=cliente,
        cita=cita,
        version_texto=ajustes.version_consentimiento,
        texto=ajustes.texto_consentimiento,
        nombre_firmante=nombre[:200],
        ip=ip,
        firma=firma,
        pdf=ContentFile(b"", name="pendiente.pdf"),
        hash_pdf="",
        respuestas={
            "fecha_nacimiento": fecha_nacimiento.strftime("%d/%m/%Y"),
            "salud": salud,
            "autoriza_fotos": autoriza_fotos,
            "acepta_marketing": acepta_marketing,
        },
        conservar_hasta=hoy.replace(year=hoy.year + ajustes.retencion_consentimientos_anios),
    )
    datos_pdf = _pdf(c, firma_bytes, ajustes)
    c.pdf.storage.delete(c.pdf.name)
    c.pdf.save(f"consentimiento-{c.pk}-{hoy:%Y%m%d}.pdf", ContentFile(datos_pdf), save=False)
    c.hash_pdf = hashlib.sha256(datos_pdf).hexdigest()
    c.save(update_fields=["pdf", "hash_pdf"])
    return c
