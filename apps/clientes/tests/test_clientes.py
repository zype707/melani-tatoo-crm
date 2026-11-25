from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.clientes.models import Cliente, DatosSalud, EventoConsentimiento, FotoTatuaje, Tatuaje
from apps.clientes.servicios import normalizar_telefono
from apps.nucleo.imagenes import procesar_imagen

pytestmark = pytest.mark.django_db


def imagen_con_exif(nombre="foto.jpg", formato="JPEG"):
    img = Image.new("RGB", (800, 600), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "MarcaDeMovil"  # Make
    exif[0x8825] = {2: (28.0, 32.0, 0.0)}  # GPSInfo
    buf = BytesIO()
    img.save(buf, formato, exif=exif.tobytes())
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type="image/jpeg")


class TestTelefono:
    @pytest.mark.parametrize(
        ("entrada", "salida"),
        [("(407) 555-0123", "+14075550123"), ("407.555.0123", "+14075550123"), ("+34 612 345 678", "+34612345678")],
    )
    def test_normaliza(self, entrada, salida):
        assert normalizar_telefono(entrada) == salida

    def test_invalido(self):
        with pytest.raises(ValidationError):
            normalizar_telefono("12")


class TestFicha:
    def test_alta_con_consentimiento_registra_evento(self, cliente_verificado):
        r = cliente_verificado.post(
            reverse("clientes:nuevo"),
            {
                "nombre": "Sofía",
                "telefono": "407 555 0199",
                "canal_preferido": "whatsapp",
                "marketing": "on",
                "marketing_origen": "presencial",
            },
        )
        assert r.status_code == 302
        sofia = Cliente.objects.get(nombre="Sofía")
        assert sofia.marketing_consentimiento
        assert sofia.marketing_origen == "presencial"
        assert EventoConsentimiento.objects.get(cliente=sofia).tipo == "alta"

    def test_consentimiento_sin_origen_no_valida(self, cliente_verificado):
        r = cliente_verificado.post(
            reverse("clientes:nuevo"),
            {"nombre": "Sofía", "telefono": "4075550199", "canal_preferido": "whatsapp", "marketing": "on"},
        )
        assert r.status_code == 200
        assert not Cliente.objects.exists()

    def test_baja_desde_ficha(self, cliente_verificado):
        c = Cliente.objects.create(nombre="Eva", telefono="+14075550111")
        c.dar_consentimiento("verbal")
        cliente_verificado.post(
            reverse("clientes:marketing", args=[c.pk]), {"accion": "baja", "origen": "peticion_baja"}
        )
        c.refresh_from_db()
        assert not c.marketing_consentimiento
        assert list(c.eventos_consentimiento.values_list("tipo", flat=True)) == ["baja", "alta"]

    def test_requiere_algun_contacto(self, cliente_verificado):
        r = cliente_verificado.post(reverse("clientes:nuevo"), {"nombre": "Sin datos", "canal_preferido": "sms"})
        assert r.status_code == 200
        assert not Cliente.objects.exists()

    def test_busqueda_sin_tildes(self):
        Cliente.objects.create(nombre="María José", telefono="+14075550123")
        assert Cliente.objects.buscar("maria").count() == 1
        assert Cliente.objects.buscar("0123").count() == 1

    def test_ficha_y_salud(self, cliente_verificado):
        c = Cliente.objects.create(nombre="Eva", telefono="+14075550111")
        cliente_verificado.post(reverse("clientes:salud", args=[c.pk]), {"alergias": "Látex", "diabetes": "on"})
        assert DatosSalud.objects.get(cliente=c).alertas() == ["Alergias", "Diabetes"]
        r = cliente_verificado.get(reverse("clientes:ficha", args=[c.pk]))
        assert r.status_code == 200
        assert "Alergias" in r.content.decode()

    def test_menor_de_edad(self):
        from django.utils import timezone

        hoy = timezone.localdate()
        c = Cliente(nombre="Joven", fecha_nacimiento=hoy.replace(year=hoy.year - 17))
        assert c.es_menor(18)
        assert not Cliente(nombre="Adulta", fecha_nacimiento=hoy.replace(year=hoy.year - 18)).es_menor(18)


class TestImagenes:
    def test_reprocesado_elimina_exif(self):
        principal, _mini = procesar_imagen(imagen_con_exif())
        limpia = Image.open(BytesIO(principal.read()))
        assert limpia.format == "JPEG"
        assert not limpia.getexif()
        assert principal.name.endswith(".jpg") and len(principal.name) == 36  # uuid aleatorio

    def test_rechaza_archivo_disfrazado(self):
        falso = SimpleUploadedFile("foto.jpg", b"<?php echo 'hola'; ?>", content_type="image/jpeg")
        with pytest.raises(ValidationError):
            procesar_imagen(falso)

    def test_rechaza_svg(self):
        svg = SimpleUploadedFile("x.png", b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')
        with pytest.raises(ValidationError):
            procesar_imagen(svg)

    def test_rechaza_demasiado_grande(self, settings):
        settings.SUBIDAS_MAX_MB = 0
        with pytest.raises(ValidationError):
            procesar_imagen(imagen_con_exif())

    def test_png_transparente_se_aplana(self):
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        buf = BytesIO()
        img.save(buf, "PNG")
        principal, _ = procesar_imagen(SimpleUploadedFile("t.png", buf.getvalue()))
        assert Image.open(BytesIO(principal.read())).mode == "RGB"


class TestArchivosPrivados:
    @pytest.fixture
    def foto(self, cliente_verificado):
        c = Cliente.objects.create(nombre="Eva", telefono="+14075550111")
        t = Tatuaje.objects.create(cliente=c, titulo="Rosa")
        cliente_verificado.post(
            reverse("clientes:subir_fotos", args=[t.pk]), {"imagenes": [imagen_con_exif()], "tipo": "resultado"}
        )
        return FotoTatuaje.objects.get()

    def test_subida_y_entrega_autenticada(self, cliente_verificado, foto):
        assert "/privado/tatuajes/" in "/" + foto.imagen.name
        r = cliente_verificado.get(reverse("clientes:foto", args=[foto.pk]))
        assert r.status_code == 200
        assert r["Content-Type"] == "image/jpeg"
        assert "no-store" in r["Cache-Control"]

    def test_anonimo_no_puede_ver_fotos(self, client, foto):
        client.logout()
        for nombre in ("clientes:foto", "clientes:foto_mini"):
            r = client.get(reverse(nombre, args=[foto.pk]))
            assert r.status_code == 302
            assert "/acceso/" in r["Location"]

    def test_media_no_se_sirve_como_estatico(self, client, foto):
        client.logout()
        assert client.get("/no-publico/" + foto.imagen.name).status_code in (302, 404)
        assert client.get("/static/../" + foto.imagen.name).status_code in (302, 404)

    def test_borrar_foto_elimina_archivo(self, cliente_verificado, foto):
        ruta = foto.imagen.path
        cliente_verificado.post(reverse("clientes:borrar_foto", args=[foto.pk]))
        import os

        assert not os.path.exists(ruta)
