from io import BytesIO

import pytest
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.agenda.forms import FIRMA_TIEMPO
from apps.agenda.models import SolicitudReserva
from apps.catalogo.models import DisenoFlash
from apps.nucleo import tokens
from apps.nucleo.models import AjustesEstudio

pytestmark = pytest.mark.django_db


def png():
    buf = BytesIO()
    Image.new("RGB", (400, 400), (240, 240, 230)).save(buf, "PNG")
    return SimpleUploadedFile("flash.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def diseno(cliente_verificado):
    cliente_verificado.post(
        reverse("catalogo:nuevo"),
        {
            "titulo": "Luna",
            "precio": "180",
            "tamano": "8 cm",
            "estado": "disponible",
            "publico": "on",
            "orden": 0,
            "archivo": png(),
        },
    )
    return DisenoFlash.objects.get()


@pytest.fixture
def catalogo_publico(db):
    a = AjustesEstudio.obtener()
    a.flash_publico = True
    a.save()
    _, token = tokens.crear_enlace("catalogo", dias=365)
    tokens.crear_enlace("reserva", dias=365)
    return token


class TestCatalogo:
    def test_alta_procesa_imagen(self, diseno):
        assert diseno.imagen.name.startswith("privado/flash/")
        assert diseno.miniatura

    def test_alta_sin_imagen_falla(self, cliente_verificado):
        r = cliente_verificado.post(reverse("catalogo:nuevo"), {"titulo": "X", "estado": "disponible", "orden": 0})
        assert r.status_code == 200 and not DisenoFlash.objects.exists()

    def test_cambio_de_estado(self, cliente_verificado, diseno, htmx):
        cliente_verificado.post(reverse("catalogo:estado", args=[diseno.pk]), {"estado": "vendido"}, **htmx)
        diseno.refresh_from_db()
        assert diseno.estado == "vendido"

    def test_pagina_publica(self, client, diseno, catalogo_publico):
        r = client.get(reverse("flash_publico", args=[catalogo_publico]))
        assert r.status_code == 200 and "Luna" in r.content.decode()
        img = client.get(reverse("flash_publico_imagen", args=[catalogo_publico, diseno.pk]))
        assert img.status_code == 200

    def test_vendido_y_privado_no_se_ven(self, client, diseno, catalogo_publico):
        diseno.estado = "vendido"
        diseno.save()
        assert "Luna" not in client.get(reverse("flash_publico", args=[catalogo_publico])).content.decode()
        assert client.get(reverse("flash_publico_imagen", args=[catalogo_publico, diseno.pk])).status_code == 404

    def test_catalogo_oculto(self, client, diseno, catalogo_publico):
        a = AjustesEstudio.obtener()
        a.flash_publico = False
        a.save()
        assert client.get(reverse("flash_publico", args=[catalogo_publico])).status_code == 404

    def test_imagen_con_token_falso(self, client, diseno):
        assert client.get(reverse("flash_publico_imagen", args=["z" * 43, diseno.pk])).status_code == 404

    def test_lo_quiero_crea_solicitud_con_diseno(self, client, diseno, catalogo_publico):
        reserva = tokens.enlace_estudio_vigente("reserva").token_visible
        url = reverse("reserva_publica", args=[reserva]) + f"?flash={diseno.pk}"
        r = client.get(url)
        assert "Flash elegido" in r.content.decode()
        t = signing.TimestampSigner(salt=FIRMA_TIEMPO).sign(str(timezone.now().timestamp() - 30))
        client.post(
            url,
            {
                "nombre": "Ana",
                "telefono": "4075550188",
                "fecha_nacimiento": "1990-01-01",
                "descripcion": "Lo quiero",
                "acepta_privacidad": "on",
                "t": t,
                "web": "",
            },
        )
        s = SolicitudReserva.objects.get()
        assert s.diseno_flash == diseno and s.descripcion.startswith("[Flash: Luna]")
