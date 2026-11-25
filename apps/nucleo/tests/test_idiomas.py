"""Interfaz bilingüe (es/en) y contenido para clientes en el idioma del estudio."""

import pytest
from django.urls import reverse
from django.utils import translation

pytestmark = pytest.mark.django_db

EN = {"HTTP_ACCEPT_LANGUAGE": "en-US,en;q=0.9"}


class TestInterfaz:
    def test_por_defecto_en_espanol(self, client):
        html = client.get(reverse("cuentas:login")).content.decode()
        assert '<html lang="es">' in html
        assert "Entrar" in html

    def test_navegador_en_ingles(self, client):
        html = client.get(reverse("cuentas:login"), **EN).content.decode()
        assert '<html lang="en">' in html
        assert "Sign in" in html and "Password" in html
        assert "Contraseña" not in html

    def test_selector_guarda_la_eleccion(self, client, settings):
        r = client.post(reverse("cambiar_idioma"), {"language": "en", "next": "/acceso/"})
        assert r.status_code == 302 and r["Location"] == "/acceso/"
        assert client.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
        assert "Sign in" in client.get("/acceso/").content.decode()

    def test_selector_no_redirige_fuera(self, client):
        r = client.post(reverse("cambiar_idioma"), {"language": "en", "next": "https://malo.example/"})
        assert r["Location"] == "/"

    def test_selector_solo_por_post(self, client):
        assert client.get(reverse("cambiar_idioma")).status_code == 405

    def test_paginas_privadas_en_ingles(self, cliente_verificado):
        cliente_verificado.post(reverse("cambiar_idioma"), {"language": "en", "next": "/"})
        html = cliente_verificado.get("/").content.decode()
        assert "Today" in html and "Sign out" in html
        html = cliente_verificado.get(reverse("clientes:lista")).content.decode()
        assert "Search clients" in html

    def test_catalogo_js(self, client):
        r = client.get(reverse("catalogo_js"), **EN)
        assert r.status_code == 200
        assert "Yes, continue" in r.content.decode()

    def test_errores_de_formulario_traducidos(self, client):
        r = client.post(reverse("cuentas:login"), {"email": "x@ejemplo.com", "password": "mala"}, **EN)
        assert "Wrong email or password." in r.content.decode()


class TestContenidoParaClientes:
    def test_variables_en_idioma_del_estudio_aunque_la_interfaz_sea_ingles(self, settings):
        from apps.mensajeria import variables

        settings.LANGUAGE_CODE = "es"
        with translation.override("en"):
            ejemplo = variables.contexto_ejemplo()
        assert ejemplo["aniversario"] == "1 año"
        assert ejemplo["fecha_cita"] == "jueves 27 de noviembre"

    def test_estudio_en_ingles(self, settings):
        from apps.mensajeria import variables

        settings.LANGUAGE_CODE = "en"
        ejemplo = variables.contexto_ejemplo()
        assert ejemplo["aniversario"] == "1 year"
        assert ejemplo["fecha_cita"] == "Thursday, November 27"

    def test_plurales(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.nucleo.templatetags.ui import relativo

        hoy = timezone.localdate()
        with translation.override("en"):
            assert relativo(hoy + timedelta(days=3)) == "in 3 days"
            assert relativo(hoy - timedelta(days=1)) == "yesterday"
        with translation.override("es"):
            assert relativo(hoy - timedelta(days=3)) == "hace 3 días"


class TestPredeterminados:
    def test_inicializar_en_ingles(self, settings):
        from django.core.management import call_command

        from apps.mensajeria.models import Plantilla
        from apps.nucleo.models import AjustesEstudio

        settings.LANGUAGE_CODE = "en"
        call_command("inicializar_estudio", verbosity=0)
        assert Plantilla.objects.filter(nombre__icontains="reminder").exists()
        assert "INFORMED CONSENT" in AjustesEstudio.obtener().texto_consentimiento
