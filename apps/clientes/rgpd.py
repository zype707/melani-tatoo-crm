"""Derechos de las personas: exportar, anonimizar o eliminar sus datos."""

import io
import json
import zipfile

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from apps.nucleo import tokens
from apps.nucleo.archivos import borrar_archivo

from .models import Cliente


def _archivo(z, campo, carpeta):
    if campo and campo.name:
        try:
            with campo.open("rb") as f:
                z.writestr(f"{carpeta}/{campo.name.rsplit('/', 1)[-1]}", f.read())
        except FileNotFoundError:
            pass


def exportar_cliente(c: Cliente) -> bytes:
    salud = getattr(c, "salud", None)
    datos = {
        "exportado_en": timezone.now(),
        "cliente": {
            "nombre": c.nombre,
            "apellidos": c.apellidos,
            "telefono": c.telefono,
            "email": c.email,
            "instagram": c.instagram,
            "fecha_nacimiento": c.fecha_nacimiento,
            "canal_preferido": c.canal_preferido,
            "acepta_promociones": c.marketing_consentimiento,
            "creado_en": c.creado_en,
            "etiquetas": [e.nombre for e in c.etiquetas.all()],
        },
        "historial_consentimiento_promociones": [
            {"tipo": e.tipo, "origen": e.origen, "fecha": e.creado_en, "notas": e.notas}
            for e in c.eventos_consentimiento.all()
        ],
        "salud": {
            k: getattr(salud, k)
            for k in (
                "alergias",
                "medicacion",
                "anticoagulantes",
                "diabetes",
                "epilepsia",
                "problemas_cardiacos",
                "embarazo_lactancia",
                "condiciones_piel",
                "otras",
            )
        }
        if salud
        else None,
        "tatuajes": [
            {
                "titulo": t.titulo,
                "zona": t.get_zona_display(),
                "estilo": t.get_estilo_display(),
                "estado": t.estado,
                "inicio": t.fecha_inicio,
                "fin": t.fecha_fin,
                "precio": t.precio_total,
                "fotos": t.fotos.count(),
            }
            for t in c.tatuajes.all()
        ],
        "citas": [
            {"inicio": x.inicio, "fin": x.fin, "tipo": x.tipo.nombre, "estado": x.estado, "descripcion": x.descripcion}
            for x in c.citas.select_related("tipo")
        ],
        "pagos": [
            {"fecha": p.fecha, "concepto": p.tipo, "importe": p.importe, "devuelto": p.devuelto} for p in c.pagos.all()
        ],
        "mensajes_enviados": [
            {"fecha": m.enviado_en, "canal": m.canal_usado, "texto": m.texto}
            for m in c.mensajes.filter(estado="enviado")
        ],
        "consentimientos_firmados": [
            {"fecha": x.firmado_en, "version": x.version_texto, "hash_pdf": x.hash_pdf} for x in c.consentimientos.all()
        ],
        "notas": [{"fecha": n.creado_en, "texto": n.texto} for n in c.notas_cliente.all()],
    }
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("datos.json", json.dumps(datos, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2))
        for t in c.tatuajes.all():
            for f in t.fotos.all():
                _archivo(z, f.imagen, "fotos")
        for x in c.consentimientos.all():
            _archivo(z, x.pdf, "consentimientos")
        for s in c.solicitudes.all():
            for i in s.imagenes.all():
                _archivo(z, i.imagen, "referencias")
    return salida.getvalue()


def consentimientos_retenidos(c: Cliente):
    return c.consentimientos.filter(conservar_hasta__gte=timezone.localdate())


@transaction.atomic
def anonimizar(c: Cliente) -> None:
    from apps.agenda.solicitudes import purgar

    hoy = timezone.localdate()
    for t in c.tatuajes.all():
        for f in t.fotos.all():
            borrar_archivo(f.imagen)
            borrar_archivo(f.miniatura)
            f.delete()
        t.titulo, t.notas, t.medidas = "Tatuaje", "", ""
        t.save(update_fields=["titulo", "notas", "medidas"])
    for x in c.consentimientos.filter(conservar_hasta__lt=hoy):
        borrar_archivo(x.pdf)
        borrar_archivo(x.firma)
        x.delete()
    for s in c.solicitudes.all():
        purgar(s)
    c.citas.update(descripcion="", notas="", notas_sesion="", motivo_cancelacion="", reprogramacion_pedida="")
    c.pagos.update(notas="")
    c.mensajes.all().delete()
    c.notas_cliente.all().delete()
    c.lista_espera.all().delete()
    if hasattr(c, "salud"):
        c.salud.delete()
    c.etiquetas.clear()
    for cita_id in c.citas.values_list("pk", flat=True):
        tokens.revocar(tokens.EnlacePublico.Proposito.CITA, cita_id)
    c.nombre, c.apellidos = "Cliente", f"anonimizado #{c.pk}"
    c.telefono = c.email = c.instagram = c.notas = ""
    c.fecha_nacimiento = None
    c.marketing_consentimiento = False
    c.contacto_bloqueado = True
    c.anonimizado_en = timezone.now()
    c.save()


def puede_eliminarse(c: Cliente) -> bool:
    return not consentimientos_retenidos(c).exists()


@transaction.atomic
def eliminar(c: Cliente) -> None:
    for t in c.tatuajes.all():
        for f in t.fotos.all():
            borrar_archivo(f.imagen)
            borrar_archivo(f.miniatura)
    for x in c.consentimientos.all():
        borrar_archivo(x.pdf)
        borrar_archivo(x.firma)
    for s in c.solicitudes.all():
        for i in s.imagenes.all():
            borrar_archivo(i.imagen)
            borrar_archivo(i.miniatura)
        s.delete()
    for cita_id in c.citas.values_list("pk", flat=True):
        tokens.revocar(tokens.EnlacePublico.Proposito.CITA, cita_id)
    c.delete()  # los pagos se conservan sin cliente (contabilidad)
