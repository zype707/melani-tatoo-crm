import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.cuentas import servicios
from apps.cuentas.models import IntentoAcceso, Usuario
from apps.nucleo.models import RegistroAuditoria
from conftest import CLAVE

pytestmark = pytest.mark.django_db

LOGIN = reverse("cuentas:login")


def _entrar(client, usuario="vale", password=CLAVE, url=LOGIN, **extra):
    return client.post(url, {"usuario": usuario, "password": password}, **extra)


def _esta_dentro(client) -> bool:
    return client.get("/").status_code == 200


class TestPaginasPrivadas:
    def test_anonima_redirige_al_login(self, client):
        r = client.get("/")
        assert r.status_code == 302
        assert r["Location"].startswith(LOGIN)

    def test_htmx_anonima_recibe_401_con_redireccion(self, client, htmx):
        r = client.get("/", **htmx)
        assert r.status_code == 401
        assert r["HX-Redirect"] == LOGIN

    def test_salud_es_publica(self, client):
        assert client.get("/salud/").content == b"ok"

    def test_no_hay_alta_ni_2fa(self, client):
        for ruta in ("/acceso/alta/", "/acceso/verificar/", "/acceso/autenticadora/", "/acceso/codigos/"):
            assert client.get(ruta).status_code == 404


class TestLogin:
    def test_usuario_y_password_correctos_entran_directamente(self, client, usuaria):
        r = _entrar(client)
        assert r.status_code == 302 and r["Location"] == reverse("panel:inicio")
        assert _esta_dentro(client)
        assert RegistroAuditoria.objects.filter(accion="login_ok", usuario=usuaria).exists()
        assert IntentoAcceso.objects.filter(usuario="vale", exito=True).count() == 1

    def test_password_incorrecta(self, client, usuaria):
        r = _entrar(client, password="mala")
        assert r.status_code == 200
        assert "Usuario o contraseña incorrectos" in r.content.decode()
        assert IntentoAcceso.objects.filter(exito=False).count() == 1
        assert RegistroAuditoria.objects.filter(descripcion__startswith="Contraseña incorrecta").exists()
        assert not _esta_dentro(client)

    def test_usuario_inexistente_mismo_mensaje(self, client, usuaria):
        r = _entrar(client, usuario="nadie")
        assert "Usuario o contraseña incorrectos" in r.content.decode()
        assert RegistroAuditoria.objects.filter(descripcion__startswith="Usuario inexistente").exists()

    def test_mayusculas_y_espacios_en_el_usuario_dan_igual(self, client, usuaria):
        _entrar(client, usuario="  VALE ")
        assert _esta_dentro(client)

    def test_cuenta_desactivada_no_entra(self, client, usuaria):
        usuaria.is_active = False
        usuaria.save()
        _entrar(client)
        assert not _esta_dentro(client)

    def test_ya_dentro_redirige_al_panel(self, cliente_verificado):
        assert cliente_verificado.get(LOGIN)["Location"] == reverse("panel:inicio")

    def test_next_externo_se_ignora(self, client, usuaria):
        r = _entrar(client, url=LOGIN + "?next=https://malo.example/")
        assert r["Location"] == reverse("panel:inicio")

    def test_next_interno_se_respeta(self, client, usuaria):
        r = _entrar(client, url=LOGIN + "?next=/cuenta/")
        assert r["Location"] == "/cuenta/"

    def test_salir_solo_por_post(self, cliente_verificado):
        assert cliente_verificado.get(reverse("cuentas:salir")).status_code == 405
        cliente_verificado.post(reverse("cuentas:salir"))
        assert cliente_verificado.get("/").status_code == 302


class TestComodidad:
    """El navegador guarda la contraseña y la sesión sobrevive al cierre del navegador."""

    def test_formulario_preparado_para_el_gestor_de_contrasenas(self, client, db):
        html = client.get(LOGIN).content.decode()
        assert 'name="usuario"' in html and 'autocomplete="username"' in html
        assert 'type="password"' in html and 'autocomplete="current-password"' in html

    def test_cookie_de_sesion_persistente_y_segura(self, client, usuaria):
        r = _entrar(client)
        cookie = r.cookies["estudio_sesion"]
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"
        assert int(cookie["max-age"]) == settings.SESSION_COOKIE_AGE  # no caduca al cerrar el navegador
        assert settings.SESSION_COOKIE_AGE == 30 * 24 * 3600


class TestBloqueo:
    def test_bloqueo_tras_fallos_aunque_luego_acierte(self, client, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_USUARIO_IP = 3
        for _ in range(3):
            _entrar(client, password="mala")
        r = _entrar(client)  # contraseña correcta, pero bloqueada
        assert "Demasiados intentos" in r.content.decode()
        assert "Location" not in r
        assert RegistroAuditoria.objects.filter(accion="login_bloqueado").exists()
        assert not _esta_dentro(client)

    def test_bloqueo_por_ip_con_usuarios_distintos(self, client, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_IP = 4
        for i in range(4):
            _entrar(client, usuario=f"x{i}", password="mala")
        assert servicios.segundos_bloqueo("vale", "127.0.0.1") > 0

    def test_exito_reinicia_contador_usuario_ip(self, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_USUARIO_IP = 3
        for _ in range(2):
            servicios.registrar_intento("vale", "1.2.3.4", False)
        servicios.registrar_intento("vale", "1.2.3.4", True)
        servicios.registrar_intento("vale", "1.2.3.4", False)
        assert servicios.segundos_bloqueo("vale", "1.2.3.4") == 0


class TestMiCuenta:
    def test_muestra_el_usuario(self, cliente_verificado):
        assert "<strong>vale</strong>" in cliente_verificado.get(reverse("cuentas:cuenta")).content.decode()

    def test_cambiar_password_mantiene_la_sesion(self, cliente_verificado, usuaria):
        nueva = "Otra-clave-bien-larga-2026"
        r = cliente_verificado.post(
            reverse("cuentas:cuenta"),
            {"accion": "password", "old_password": CLAVE, "new_password1": nueva, "new_password2": nueva},
        )
        assert r.status_code == 302
        usuaria.refresh_from_db()
        assert usuaria.check_password(nueva)
        assert _esta_dentro(cliente_verificado)
        assert RegistroAuditoria.objects.filter(accion="password_cambiada").exists()

    def test_password_parecida_al_usuario_se_rechaza(self, cliente_verificado):
        r = cliente_verificado.post(
            reverse("cuentas:cuenta"),
            {
                "accion": "password",
                "old_password": CLAVE,
                "new_password1": "vale-rios-1",
                "new_password2": "vale-rios-1",
            },
        )
        assert r.status_code == 200


class TestCrearCuenta:
    @pytest.fixture
    def clave_env(self, monkeypatch):
        monkeypatch.setenv("CLAVE_PRUEBA", "Otra-clave-muy-larga-2026")
        return "CLAVE_PRUEBA"

    def test_crea_cuenta(self, clave_env):
        call_command("crear_cuenta", usuario="Mels", nombre="Mels", password_env=clave_env)
        u = Usuario.objects.get(usuario="mels")
        assert u.password.startswith(("argon2", "md5"))
        assert u.es_propietaria and u.check_password("Otra-clave-muy-larga-2026")

    def test_ayudante(self, clave_env):
        call_command("crear_cuenta", usuario="ayu", rol="ayudante", password_env=clave_env)
        assert not Usuario.objects.get(usuario="ayu").es_propietaria

    def test_rechaza_duplicado_sin_tocar_la_existente(self, usuaria, clave_env):
        with pytest.raises(CommandError, match="Ya existe"):
            call_command("crear_cuenta", usuario="VALE", password_env=clave_env)
        usuaria.refresh_from_db()
        assert usuaria.check_password(CLAVE)

    def test_rechaza_usuario_con_espacios(self, clave_env):
        with pytest.raises(CommandError):
            call_command("crear_cuenta", usuario="mi usuaria", password_env=clave_env)
        assert not Usuario.objects.exists()

    def test_rechaza_clave_debil(self, monkeypatch):
        monkeypatch.setenv("CLAVE_PRUEBA", "123")
        with pytest.raises(CommandError):
            call_command("crear_cuenta", usuario="b", password_env="CLAVE_PRUEBA")
        assert not Usuario.objects.exists()


class TestCuentaDesdeEntorno:
    """Pre-deploy: PROPIETARIA_USUARIO + PROPIETARIA_PASSWORD crean la cuenta sin pasos en la web."""

    def test_crea_la_propietaria(self, client, monkeypatch):
        monkeypatch.setenv("PROPIETARIA_USUARIO", "Ink_Mels")
        monkeypatch.setenv("PROPIETARIA_PASSWORD", "Clave-del-despliegue-2026")
        monkeypatch.setenv("PROPIETARIA_NOMBRE", "Mels")
        call_command("crear_cuenta", "--desde-entorno")
        u = Usuario.objects.get(usuario="ink_mels")
        assert u.es_propietaria and u.nombre == "Mels"
        _entrar(client, usuario="ink_mels", password="Clave-del-despliegue-2026")
        assert _esta_dentro(client)

    def test_no_toca_una_cuenta_existente(self, usuaria, monkeypatch):
        monkeypatch.setenv("PROPIETARIA_USUARIO", "vale")
        monkeypatch.setenv("PROPIETARIA_PASSWORD", "Una-clave-distinta-2026")
        call_command("crear_cuenta", "--desde-entorno")
        usuaria.refresh_from_db()
        assert usuaria.check_password(CLAVE)  # la contraseña cambiada en «Mi cuenta» se respeta

    def test_sin_variables_no_hace_nada(self, monkeypatch, db):
        monkeypatch.delenv("PROPIETARIA_USUARIO", raising=False)
        call_command("crear_cuenta", "--desde-entorno")
        assert not Usuario.objects.exists()

    def test_usuario_sin_password_falla(self, monkeypatch, db):
        monkeypatch.setenv("PROPIETARIA_USUARIO", "mels")
        monkeypatch.delenv("PROPIETARIA_PASSWORD", raising=False)
        with pytest.raises(CommandError, match="PROPIETARIA_PASSWORD"):
            call_command("crear_cuenta", "--desde-entorno")

    def test_usuario_ya_creado_y_sin_password_no_falla(self, usuaria, monkeypatch):
        """Tras el primer despliegue se puede borrar PROPIETARIA_PASSWORD de Render."""
        monkeypatch.setenv("PROPIETARIA_USUARIO", "vale")
        monkeypatch.delenv("PROPIETARIA_PASSWORD", raising=False)
        call_command("crear_cuenta", "--desde-entorno")


class TestUsuarioDesdeEmail:
    def test_sin_repetir(self):
        ocupados = set()
        assert servicios.usuario_desde_email("Vale@ejemplo.com", ocupados) == "vale"
        assert servicios.usuario_desde_email("vale@otro.com", ocupados) == "vale2"
        assert servicios.usuario_desde_email("", ocupados, "usuaria7") == "usuaria7"
        assert servicios.usuario_desde_email("raro!#@x.com", ocupados) == "raro"
