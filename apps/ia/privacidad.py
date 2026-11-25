"""Qué puede salir hacia la IA: el mínimo imprescindible.

NUNCA se envían: datos de salud, fecha de nacimiento, apellidos, teléfono,
email, Instagram, notas privadas, notas de sesión, consentimientos, firmas,
documentos ni imágenes. Los textos libres pasan antes por `redactar_pii`.
"""

import re

from django.utils import timezone

PATRONES = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[enlace]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[documento]"),  # SSN
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[número]"),  # tarjetas
    (re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)"), "[teléfono]"),
    (re.compile(r"@[A-Za-z0-9_.]{2,30}"), "[usuario]"),
]


def redactar_pii(texto: str, limite: int = 2000) -> str:
    texto = (texto or "")[:limite]
    for patron, sustituto in PATRONES:
        texto = patron.sub(sustituto, texto)
    return texto.strip()


def perfil_cliente(cliente) -> dict:
    """Ficha mínima y sin datos sensibles para personalizar un texto."""
    from apps.agenda.models import EstadoCita

    hoy = timezone.localdate()
    citas = list(cliente.citas.select_related("tipo").order_by("-inicio")[:6])
    realizadas = cliente.citas.filter(estado=EstadoCita.REALIZADA).count()
    futuras = [c for c in citas if c.inicio > timezone.now() and c.estado in ("solicitada", "confirmada")]
    return {
        "nombre": cliente.nombre.split()[0] if cliente.nombre else "",
        "cliente_desde": cliente.creado_en.year,
        "visitas": realizadas,
        "acepta_promociones": cliente.marketing_consentimiento,
        "etiquetas": [e.nombre for e in cliente.etiquetas.all()][:6],
        "tatuajes": [
            {
                "titulo": redactar_pii(t.titulo, 80),
                "zona": t.get_zona_display() if t.zona else "",
                "estilo": t.get_estilo_display() if t.estilo else "",
                "tamano": t.get_tamano_display() if t.tamano else "",
                "estado": t.get_estado_display(),
                "anio": t.fecha_aniversario.year if t.fecha_aniversario else None,
            }
            for t in cliente.tatuajes.all()[:6]
        ],
        "ultimas_citas": [
            {
                "hace_dias": (hoy - timezone.localtime(c.inicio).date()).days,
                "tipo": c.tipo.nombre,
                "estado": c.get_estado_display(),
            }
            for c in citas
            if c not in futuras
        ][:4],
        "proxima_cita": (
            {"en_dias": (timezone.localtime(futuras[-1].inicio).date() - hoy).days, "tipo": futuras[-1].tipo.nombre}
            if futuras
            else None
        ),
    }
