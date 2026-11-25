import importlib
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.nucleo import limites, tokens
from apps.nucleo.models import EnlacePublico
from apps.nucleo.red import ip_cliente

pytestmark = pytest.mark.django_db


class TestCabeceras:
    def test_cabeceras_de_seguridad(self, client):
        r = client.get("/acceso/")
        csp = r["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp.split("style-src-attr")[0]  # ni scripts ni <style> en línea
        assert "frame-ancestors 'none'" in csp
        assert r["X-Frame-Options"] == "DENY"
        assert r["X-Content-Type-Options"] == "nosniff"
        assert r["Referrer-Policy"] == "same-origin"
        assert "geolocation=()" in r["Permissions-Policy"]

    def test_paginas_privadas_no_se_cachean(self, cliente_verificado):
        r = cliente_verificado.get("/")
        assert "no-store" in r["Cache-Control"]

    def test_ajustes_de_produccion(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "x" * 50)
        importlib.reload(importlib.import_module("estudio.settings.base"))
        prod = importlib.reload(importlib.import_module("estudio.settings.prod"))
        assert prod.DEBUG is False
        assert prod.SESSION_COOKIE_SECURE and prod.CSRF_COOKIE_SECURE
        assert prod.SESSION_COOKIE_HTTPONLY
        assert prod.SESSION_COOKIE_SAMESITE == "Lax"
        assert prod.SECURE_HSTS_SECONDS >= 31536000
        assert prod.SECURE_SSL_REDIRECT
        assert prod.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")

    def test_produccion_sin_secret_key_falla(self, monkeypatch):
        from django.core.exceptions import ImproperlyConfigured

        monkeypatch.setenv("SECRET_KEY", "")
        import estudio.settings.base as base

        importlib.reload(base)
        with pytest.raises(ImproperlyConfigured):
            importlib.reload(importlib.import_module("estudio.settings.prod"))
        monkeypatch.setenv("SECRET_KEY", "x" * 50)
        importlib.reload(base)


class TestTokens:
    def test_token_valido(self):
        enlace, token = tokens.crear_enlace("cita", objeto_id=7)
        assert len(token) == 43
        assert tokens.resolver("cita", token) == enlace

    def test_cita_guarda_solo_el_hash(self):
        enlace, token = tokens.crear_enlace("cita", objeto_id=7)
        assert enlace.token_visible == ""
        assert token not in enlace.token_hash
        assert enlace.token_hash == tokens.hash_token(token)

    def test_enlace_de_reserva_es_visible(self):
        enlace, token = tokens.crear_enlace("reserva")
        assert enlace.token_visible == token

    def test_caducado(self):
        _, token = tokens.crear_enlace("cita", caduca_en=timezone.now() - timedelta(seconds=1))
        assert tokens.resolver("cita", token) is None

    def test_revocado(self):
        _, token = tokens.crear_enlace("cita", objeto_id=3)
        tokens.revocar("cita", 3)
        assert tokens.resolver("cita", token) is None

    def test_proposito_distinto(self):
        _, token = tokens.crear_enlace("reserva")
        assert tokens.resolver("cita", token) is None

    @pytest.mark.parametrize("malo", ["", "abc", "x" * 43, "../../etc/passwd", "a" * 42 + "!", "a" * 200])
    def test_tokens_invalidos(self, malo):
        tokens.crear_enlace("cita")
        assert tokens.resolver("cita", malo) is None

    def test_cuenta_usos(self):
        enlace, token = tokens.crear_enlace("cita")
        tokens.resolver("cita", token)
        tokens.resolver("cita", token)
        enlace.refresh_from_db()
        assert enlace.usos == 2
        assert EnlacePublico.objects.count() == 1


class TestLimites:
    def test_superado(self):
        assert not any(limites.superado("prueba", 3, 60) for _ in range(3))
        assert limites.superado("prueba", 3, 60)

    def test_ip_con_proxy_de_confianza(self, settings):
        rf = RequestFactory()
        settings.PROXIES_DE_CONFIANZA = 1
        req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", REMOTE_ADDR="10.0.0.1")
        assert ip_cliente(req) == "203.0.113.9"  # la falseada por el cliente se ignora
        settings.PROXIES_DE_CONFIANZA = 0
        assert ip_cliente(req) == "10.0.0.1"


class TestComandos:
    def test_crear_cuenta(self, monkeypatch):
        monkeypatch.setenv("CLAVE_PRUEBA", "Otra-clave-muy-larga-2026")
        call_command("crear_cuenta", email="Ana@Ejemplo.com", nombre="Ana", password_env="CLAVE_PRUEBA")
        u = Usuario.objects.get(email="ana@ejemplo.com")
        assert u.password.startswith(("argon2", "md5"))
        assert u.es_propietaria

    def test_crear_cuenta_rechaza_clave_debil(self, monkeypatch):
        from django.core.management.base import CommandError

        monkeypatch.setenv("CLAVE_PRUEBA", "123")
        with pytest.raises(CommandError):
            call_command("crear_cuenta", email="b@ejemplo.com", password_env="CLAVE_PRUEBA")

    def test_argon2_en_produccion(self):
        from django.contrib.auth.hashers import make_password

        assert make_password("x", hasher="argon2").startswith("argon2$argon2id$")
