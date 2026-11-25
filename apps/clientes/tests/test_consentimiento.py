import base64
import hashlib
from io import BytesIO

import pytest
from django.urls import reverse
from PIL import Image, ImageDraw

from apps.clientes.models import Cliente, ConsentimientoInformado, DatosSalud
from apps.nucleo.models import RegistroAuditoria

pytestmark = pytest.mark.django_db


def firma(vacia=False):
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    if not vacia:
        d = ImageDraw.Draw(img)
        d.line([(40, 150), (200, 40), (380, 160), (560, 60)], fill=(1, 22, 27, 255), width=5)
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(nombre="Lucía", apellidos="Méndez", telefono="+14075550123")


def datos(**extra):
    base = {
        "nombre_firmante": "Lucía Méndez",
        "fecha_nacimiento": "1994-03-12",
        "alergias": "Látex",
        "diabetes": "on",
        "acepto": "on",
        "veraz": "on",
        "autoriza_fotos": "on",
        "firma": firma(),
    }
    base.update(extra)
    return base


class TestConsentimiento:
    def test_firma_genera_pdf_y_actualiza_salud(self, cliente_verificado, cliente):
        url = reverse("clientes:consentimiento", args=[cliente.pk])
        assert cliente_verificado.get(url).status_code == 200
        r = cliente_verificado.post(url, datos())
        assert r.status_code == 200 and "Gracias" in r.content.decode()
        c = ConsentimientoInformado.objects.get()
        contenido = c.pdf.read()
        assert contenido.startswith(b"%PDF")
        assert hashlib.sha256(contenido).hexdigest() == c.hash_pdf
        assert c.respuestas["salud"]["alergias"] == "Látex"
        assert c.respuestas["autoriza_fotos"] is True
        assert "CONSENTIMIENTO INFORMADO" in c.texto
        assert c.conservar_hasta.year == c.firmado_en.year + 2
        assert DatosSalud.objects.get(cliente=cliente).diabetes
        assert c.firma.name.startswith("privado/consentimientos/")

    def test_firma_vacia_rechazada(self, cliente_verificado, cliente):
        r = cliente_verificado.post(
            reverse("clientes:consentimiento", args=[cliente.pk]), datos(firma=firma(vacia=True))
        )
        assert r.status_code == 200
        assert not ConsentimientoInformado.objects.exists()

    def test_firma_no_png_rechazada(self, cliente_verificado, cliente):
        malo = "data:image/png;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode()
        cliente_verificado.post(reverse("clientes:consentimiento", args=[cliente.pk]), datos(firma=malo))
        assert not ConsentimientoInformado.objects.exists()

    def test_sin_aceptar_no_firma(self, cliente_verificado, cliente):
        cliente_verificado.post(reverse("clientes:consentimiento", args=[cliente.pk]), datos(acepto=""))
        assert not ConsentimientoInformado.objects.exists()

    def test_menor_no_firma(self, cliente_verificado, cliente):
        from django.utils import timezone

        hoy = timezone.localdate()
        n = hoy.replace(year=hoy.year - 17).isoformat()
        cliente_verificado.post(reverse("clientes:consentimiento", args=[cliente.pk]), datos(fecha_nacimiento=n))
        assert not ConsentimientoInformado.objects.exists()

    def test_marketing_desde_consentimiento(self, cliente_verificado, cliente):
        cliente_verificado.post(reverse("clientes:consentimiento", args=[cliente.pk]), datos(acepta_marketing="on"))
        cliente.refresh_from_db()
        assert cliente.marketing_consentimiento and cliente.marketing_origen == "presencial"

    def test_pdf_privado_y_auditado(self, cliente_verificado, cliente, client):
        cliente_verificado.post(reverse("clientes:consentimiento", args=[cliente.pk]), datos())
        c = ConsentimientoInformado.objects.get()
        url = reverse("clientes:consentimiento_pdf", args=[c.pk])
        r = cliente_verificado.get(url)
        assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
        assert RegistroAuditoria.objects.filter(accion="acceso_documento").exists()
        cliente_verificado.logout()
        assert cliente_verificado.get(url).status_code == 302
