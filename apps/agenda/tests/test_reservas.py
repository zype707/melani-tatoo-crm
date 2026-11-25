import time
from datetime import date
from io import BytesIO

import pytest
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.agenda.forms import FIRMA_TIEMPO
from apps.agenda.models import SolicitudReserva
from apps.clientes.models import Cliente, FotoTatuaje
from apps.mensajeria.predeterminados import crear_predeterminados
from apps.nucleo import tokens
from apps.nucleo.models import AjustesEstudio

pytestmark = pytest.mark.django_db


def png(nombre="ref.png"):
    buf = BytesIO()
    Image.new("RGB", (300, 300), (10, 120, 80)).save(buf, "PNG")
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type="image/png")


def tiempo_valido():
    return signing.TimestampSigner(salt=FIRMA_TIEMPO).sign(str(timezone.now().timestamp() - 30))


def datos(**extra):
    base = {
        "nombre": "Sofía",
        "apellidos": "Luna",
        "telefono": "(407) 555-0190",
        "email": "sofia@ejemplo.com",
        "fecha_nacimiento": "1995-04-02",
        "descripcion": "Una luna fine line en el antebrazo",
        "zona": "antebrazo",
        "tamano": "pequeno",
        "estilo": "fine_line",
        "acepta_privacidad": "on",
        "acepta_marketing": "on",
        "t": tiempo_valido(),
        "web": "",
    }
    base.update(extra)
    return base


@pytest.fixture
def url_reserva(db):
    _, token = tokens.crear_enlace("reserva", dias=365)
    return reverse("reserva_publica", args=[token])


class TestPaginaPublica:
    def test_muestra_formulario(self, client, url_reserva):
        r = client.get(url_reserva)
        assert r.status_code == 200
        assert "Pide tu cita" in r.content.decode()

    def test_token_invalido(self, client, db):
        assert client.get(reverse("reserva_publica", args=["a" * 43])).status_code == 404

    def test_envio_con_imagenes(self, client, url_reserva):
        r = client.post(url_reserva, {**datos(), "imagenes": [png(), png("b.png")]})
        assert r.status_code == 302, r.content.decode()[:500]
        s = SolicitudReserva.objects.get()
        assert s.telefono == "+14075550190"
        assert s.imagenes.count() == 2
        assert s.huella_ip and "127.0.0.1" not in s.huella_ip
        assert s.imagenes.first().imagen.name.startswith("privado/solicitudes/")

    def test_menor_rechazado(self, client, url_reserva):
        hoy = timezone.localdate()
        r = client.post(url_reserva, datos(fecha_nacimiento=date(hoy.year - 16, 1, 1).isoformat()))
        assert r.status_code == 200
        assert "al menos 18" in r.content.decode()
        assert not SolicitudReserva.objects.exists()

    def test_campo_trampa(self, client, url_reserva):
        client.post(url_reserva, datos(web="http://spam.example"))
        assert not SolicitudReserva.objects.exists()

    def test_envio_demasiado_rapido(self, client, url_reserva):
        rapido = signing.TimestampSigner(salt=FIRMA_TIEMPO).sign(str(timezone.now().timestamp()))
        client.post(url_reserva, datos(t=rapido))
        assert not SolicitudReserva.objects.exists()

    def test_imagen_falsa_rechazada(self, client, url_reserva):
        falsa = SimpleUploadedFile("x.jpg", b"GIF89a<script>alert(1)</script>", content_type="image/jpeg")
        r = client.post(url_reserva, {**datos(), "imagenes": [falsa]})
        assert r.status_code == 200
        assert not SolicitudReserva.objects.exists()

    def test_demasiadas_imagenes(self, client, url_reserva, settings):
        settings.SUBIDAS_MAX_IMAGENES = 2
        r = client.post(url_reserva, {**datos(), "imagenes": [png(), png(), png()]})
        assert "Como máximo 2" in r.content.decode()

    def test_limite_de_envios(self, client, url_reserva):
        for _ in range(5):
            client.post(url_reserva, datos(t="malo"))
        assert client.post(url_reserva, datos()).status_code == 429

    def test_agenda_cerrada(self, client, url_reserva):
        a = AjustesEstudio.obtener()
        a.reservas_activas = False
        a.save()
        assert "Agenda cerrada" in client.get(url_reserva).content.decode()

    def test_imagenes_privadas(self, client, url_reserva):
        client.post(url_reserva, {**datos(), "imagenes": [png()]})
        img = SolicitudReserva.objects.get().imagenes.get()
        assert client.get(reverse("solicitudes:imagen", args=[img.pk])).status_code == 302


class TestBandejaSolicitudes:
    @pytest.fixture
    def solicitud(self, client, url_reserva):
        crear_predeterminados()
        client.post(url_reserva, {**datos(), "imagenes": [png()]})
        return SolicitudReserva.objects.get()

    def test_aceptar_crea_ficha_tatuaje_y_mensaje(self, cliente_verificado, solicitud):
        r = cliente_verificado.post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
        solicitud.refresh_from_db()
        assert solicitud.estado == SolicitudReserva.Estado.APROBADA
        c = solicitud.cliente
        assert c.marketing_consentimiento and c.marketing_origen == "formulario"
        assert solicitud.tatuaje.zona == "antebrazo"
        assert FotoTatuaje.objects.filter(tatuaje=solicitud.tatuaje, tipo="referencia").count() == 1
        assert "/mensajes/" in r["Location"]

    def test_reutiliza_cliente_existente(self, cliente_verificado, solicitud):
        existente = Cliente.objects.create(nombre="Sofi", telefono="+14075550190")
        cliente_verificado.post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
        solicitud.refresh_from_db()
        assert solicitud.cliente == existente
        assert Cliente.objects.count() == 1

    def test_dar_cita_marca_convertida(self, cliente_verificado, solicitud):
        from apps.agenda.models import TipoCita

        r = cliente_verificado.post(reverse("solicitudes:convertir", args=[solicitud.pk]))
        assert r["Location"].startswith(reverse("agenda:nueva"))
        solicitud.refresh_from_db()
        tipo = TipoCita.objects.get(nombre="Sesión")
        fecha = (timezone.localdate() + timezone.timedelta(days=9)).isoformat()
        cliente_verificado.post(
            r["Location"],
            {
                "cliente": solicitud.cliente.pk,
                "tipo": tipo.pk,
                "estado": "confirmada",
                "fecha": fecha,
                "hora": "12:00",
                "duracion": 120,
                "tatuaje": solicitud.tatuaje.pk,
                "fuera_de_horario": "on",
            },
        )
        solicitud.refresh_from_db()
        assert solicitud.estado == SolicitudReserva.Estado.CONVERTIDA
        assert solicitud.cita is not None

    def test_spam_borra_datos_e_imagenes(self, cliente_verificado, solicitud):
        ruta = solicitud.imagenes.get().imagen.path
        cliente_verificado.post(reverse("solicitudes:rechazar", args=[solicitud.pk]), {"spam": "1"})
        solicitud.refresh_from_db()
        import os

        assert solicitud.telefono == "" and not solicitud.imagenes.exists()
        assert not os.path.exists(ruta)

    def test_lista_y_detalle(self, cliente_verificado, solicitud):
        assert "Sofía" in cliente_verificado.get(reverse("solicitudes:lista")).content.decode()
        r = cliente_verificado.get(reverse("solicitudes:detalle", args=[solicitud.pk]))
        assert r.status_code == 200
        assert "wa.me/14075550190" in r.content.decode()

    def test_renovar_enlace_invalida_el_anterior(self, cliente_verificado, url_reserva, client):
        cliente_verificado.post(reverse("solicitudes:enlace"), {"accion": "renovar"})
        time.sleep(0)
        assert client.get(url_reserva).status_code == 404
