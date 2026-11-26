import io
import json
import os
import time
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

from apps.clientes.models import Cliente, DatosSalud
from apps.cuentas.models import Usuario
from apps.nucleo.models import AjustesEstudio, RegistroAuditoria
from conftest import CLAVE

pytestmark = pytest.mark.django_db
URL_TAREA = "/interno/tareas/limpiar_archivos/"
SECRETO = "s" * 40


class TestTareasInternas:
    def test_sin_secreto_configurado(self, client, settings):
        settings.TAREAS_SECRETO = ""
        assert client.post(URL_TAREA).status_code == 404

    def test_secreto_incorrecto(self, client, settings):
        settings.TAREAS_SECRETO = SECRETO
        assert client.post(URL_TAREA, HTTP_AUTHORIZATION="Bearer otro").status_code == 403
        assert RegistroAuditoria.objects.filter(accion="tarea").exists()

    def test_tarea_desconocida(self, client, settings):
        settings.TAREAS_SECRETO = SECRETO
        assert client.post("/interno/tareas/flush/", HTTP_AUTHORIZATION=f"Bearer {SECRETO}").status_code == 404

    def test_get_no_permitido(self, client, settings):
        settings.TAREAS_SECRETO = SECRETO
        assert client.get(URL_TAREA, HTTP_AUTHORIZATION=f"Bearer {SECRETO}").status_code == 405

    def test_ejecuta(self, client, settings):
        settings.TAREAS_SECRETO = SECRETO
        r = client.post(URL_TAREA, HTTP_AUTHORIZATION=f"Bearer {SECRETO}")
        assert r.status_code == 200 and r.json()["tarea"] == "limpiar_archivos"


class TestArchivos:
    def test_borra_huerfanos_antiguos(self):
        raiz = Path(settings.MEDIA_ROOT) / "privado" / "prueba"
        raiz.mkdir(parents=True, exist_ok=True)
        viejo, nuevo = raiz / "viejo.jpg", raiz / "nuevo.jpg"
        viejo.write_bytes(b"x")
        nuevo.write_bytes(b"x")
        hace_dos_dias = time.time() - 48 * 3600
        os.utime(viejo, (hace_dos_dias, hace_dos_dias))
        call_command("limpiar_archivos", stdout=io.StringIO())
        assert not viejo.exists() and nuevo.exists()

    def test_copia_de_seguridad_con_rotacion(self, settings, usuaria):
        settings.COPIAS_A_CONSERVAR = 2
        for _ in range(3):
            call_command("copia_seguridad", stdout=io.StringIO())
            time.sleep(1.05)
        copias = sorted(Path(settings.COPIAS_ROOT).glob("copia-*.zip"))
        assert len(copias) == 2
        with zipfile.ZipFile(copias[-1]) as z:
            datos = json.loads(z.read("datos.json"))
        assert any(d["model"] == "cuentas.usuario" for d in datos)  # la copia permite restaurar todo


class TestExportacion:
    def test_requiere_password_y_excluye_credenciales(self, cliente_verificado):
        Cliente.objects.create(nombre="Eva", telefono="+14075550111")
        r = cliente_verificado.post(reverse("nucleo:exportar"), {"password": "mala"})
        assert r.status_code == 302
        r = cliente_verificado.post(reverse("nucleo:exportar"), {"password": CLAVE})
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(b"".join(r.streaming_content))) as z:
            datos = json.loads(z.read("datos.json"))
        modelos = {d["model"] for d in datos}
        assert "clientes.cliente" in modelos
        assert not any(m.startswith("cuentas.") for m in modelos)
        assert RegistroAuditoria.objects.filter(accion="exportacion").exists()

    def test_confirmar_password_tiene_limite_de_intentos(self, cliente_verificado):
        for _ in range(10):
            cliente_verificado.post(reverse("nucleo:exportar"), {"password": "mala"})
        r = cliente_verificado.post(reverse("nucleo:exportar"), {"password": CLAVE})
        assert r.status_code == 302  # bloqueada aunque ahora acierte

    def test_comando_exportar(self, tmp_path):
        destino = tmp_path / "e.zip"
        call_command("exportar_datos", salida=str(destino), stdout=io.StringIO())
        assert zipfile.is_zipfile(destino)


class TestRGPD:
    @pytest.fixture
    def eva(self):
        c = Cliente.objects.create(nombre="Eva", apellidos="Luna", telefono="+14075550111", email="eva@x.com")
        DatosSalud.objects.create(cliente=c, alergias="Látex")
        return c

    def test_exportar_cliente(self, cliente_verificado, eva):
        r = cliente_verificado.get(reverse("clientes:exportar", args=[eva.pk]))
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            datos = json.loads(z.read("datos.json"))
        assert datos["cliente"]["email"] == "eva@x.com" and datos["salud"]["alergias"] == "Látex"

    def test_anonimizar(self, cliente_verificado, eva):
        r = cliente_verificado.post(reverse("clientes:anonimizar", args=[eva.pk]), {"confirmar_nombre": "eva luna"})
        assert r.status_code == 302
        eva.refresh_from_db()
        assert eva.anonimizado and eva.telefono == "" and eva.email == ""
        assert not DatosSalud.objects.filter(cliente=eva).exists()
        assert eva.contacto_bloqueado
        assert RegistroAuditoria.objects.filter(accion="anonimizacion").exists()

    def test_confirmacion_obligatoria(self, cliente_verificado, eva):
        cliente_verificado.post(reverse("clientes:eliminar", args=[eva.pk]), {"confirmar_nombre": "otra"})
        assert Cliente.objects.filter(pk=eva.pk).exists()

    def test_eliminar(self, cliente_verificado, eva):
        cliente_verificado.post(reverse("clientes:eliminar", args=[eva.pk]), {"confirmar_nombre": "Eva Luna"})
        assert not Cliente.objects.filter(pk=eva.pk).exists()


class TestAjustesYPWA:
    def test_cambiar_consentimiento_sube_version(self, cliente_verificado):
        cliente_verificado.post(
            reverse("nucleo:ajustes") + "?seccion=legal",
            {"texto_consentimiento": "Texto nuevo", "retencion_consentimientos_anios": 3},
        )
        a = AjustesEstudio.obtener()
        assert a.version_consentimiento == 2 and a.retencion_consentimientos_anios == 3

    def test_edad_minima_florida(self, cliente_verificado):
        r = cliente_verificado.post(
            reverse("nucleo:ajustes") + "?seccion=reservas",
            {
                "edad_minima": 15,
                "reserva_bienvenida": "x",
                "politica_senas": "x",
                "texto_cuidados": "x",
                "texto_privacidad": "x",
            },
        )
        assert "16 años" in r.content.decode()

    def test_ayudante_sin_ajustes(self, client):
        u = Usuario.objects.create_user("ayudante", "Clave-larguisima-2026", nombre="A", rol="ayudante")
        client.force_login(u)
        assert client.get(reverse("nucleo:ajustes")).status_code == 403

    def test_manifest_y_service_worker(self, client, db):
        m = client.get("/manifest.webmanifest")
        assert m.status_code == 200 and json.loads(m.content)["display"] == "standalone"
        sw = client.get("/sw.js")
        assert sw["Service-Worker-Allowed"] == "/" and b"caches" in sw.content
        assert client.get("/offline/").status_code == 200
