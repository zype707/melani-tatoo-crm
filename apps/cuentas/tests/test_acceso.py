import time

import pytest
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.cuentas import servicios
from apps.cuentas.models import CodigoRecuperacion, IntentoAcceso
from apps.nucleo.models import RegistroAuditoria
from conftest import CLAVE, codigo_totp

pytestmark = pytest.mark.django_db

LOGIN = reverse("cuentas:login")
VERIFICAR = reverse("cuentas:verificar")
CONFIGURAR = reverse("cuentas:configurar_2fa")


def _entrar_con_password(client, email="vale@ejemplo.com", password=CLAVE, **extra):
    return client.post(LOGIN, {"email": email, "password": password}, **extra)


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

    def test_sesion_sin_segundo_factor_no_basta(self, client, usuaria):
        client.force_login(usuaria)  # contraseña OK pero sin OTP verificado
        r = client.get("/")
        assert r.status_code == 302
        assert "_auth_user_id" not in client.session  # se cierra la sesión a medias

    def test_salud_es_publica(self, client):
        assert client.get("/salud/").content == b"ok"


class TestLogin:
    def test_password_incorrecta(self, client, usuaria):
        r = _entrar_con_password(client, password="mala")
        assert r.status_code == 200
        assert "incorrectos" in r.content.decode()
        assert IntentoAcceso.objects.filter(exito=False).count() == 1
        assert RegistroAuditoria.objects.filter(accion="login_fallo").exists()
        assert not _esta_dentro(client)

    def test_email_inexistente_mismo_mensaje(self, client, usuaria):
        r = _entrar_con_password(client, email="nadie@ejemplo.com")
        assert "Email o contraseña incorrectos" in r.content.decode()

    def test_primer_acceso_obliga_a_configurar_2fa(self, client, usuaria):
        r = _entrar_con_password(client)
        assert r["Location"] == CONFIGURAR
        assert not _esta_dentro(client)  # la contraseña sola no da acceso

    def test_con_2fa_pide_codigo(self, client, dispositivo):
        r = _entrar_con_password(client)
        assert r["Location"] == VERIFICAR
        assert not _esta_dentro(client)

    def test_flujo_completo_con_totp(self, client, dispositivo):
        _entrar_con_password(client)
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        assert r.status_code == 302
        assert _esta_dentro(client)
        assert RegistroAuditoria.objects.filter(accion="login_ok").exists()

    def test_totp_incorrecto(self, client, dispositivo):
        _entrar_con_password(client)
        r = client.post(VERIFICAR, {"codigo": "000000"})
        assert r.status_code == 200
        assert not _esta_dentro(client)

    def test_codigo_totp_no_se_puede_reutilizar(self, client, dispositivo):
        _entrar_con_password(client)
        codigo = codigo_totp(dispositivo)
        client.post(VERIFICAR, {"codigo": codigo})
        client.post(reverse("cuentas:salir"))
        _entrar_con_password(client)
        client.post(VERIFICAR, {"codigo": codigo})
        assert not _esta_dentro(client)

    def test_next_externo_se_ignora(self, client, dispositivo):
        client.post(LOGIN + "?next=https://malo.example/", {"email": "vale@ejemplo.com", "password": CLAVE})
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        assert r["Location"] == reverse("panel:inicio")

    def test_next_interno_se_respeta(self, client, dispositivo):
        client.post(LOGIN + "?next=/cuenta/", {"email": "vale@ejemplo.com", "password": CLAVE})
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        assert r["Location"] == "/cuenta/"

    def test_preauth_caduca(self, client, dispositivo, settings):
        _entrar_con_password(client)
        sesion = client.session
        sesion[servicios.CLAVE_PREAUTH]["ts"] = time.time() - 3600
        sesion.save()
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        assert r["Location"] == LOGIN
        assert not _esta_dentro(client)

    def test_salir_solo_por_post(self, cliente_verificado):
        assert cliente_verificado.get(reverse("cuentas:salir")).status_code == 405
        cliente_verificado.post(reverse("cuentas:salir"))
        assert cliente_verificado.get("/").status_code == 302

    def test_cookie_de_sesion_httponly(self, client, dispositivo):
        _entrar_con_password(client)
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        cookie = r.cookies["estudio_sesion"]
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"


class TestBloqueo:
    def test_bloqueo_tras_fallos_aunque_luego_acierte(self, client, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_EMAIL_IP = 3
        for _ in range(3):
            _entrar_con_password(client, password="mala")
        r = _entrar_con_password(client)  # contraseña correcta, pero bloqueada
        assert "Demasiados intentos" in r.content.decode()
        assert "Location" not in r
        assert RegistroAuditoria.objects.filter(accion="login_bloqueado").exists()

    def test_bloqueo_por_ip_con_emails_distintos(self, client, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_IP = 4
        for i in range(4):
            _entrar_con_password(client, email=f"x{i}@ejemplo.com", password="mala")
        assert servicios.segundos_bloqueo("vale@ejemplo.com", "127.0.0.1") > 0

    def test_exito_reinicia_contador_email_ip(self, usuaria, settings):
        settings.ACCESO_MAX_FALLOS_EMAIL_IP = 3
        for _ in range(2):
            servicios.registrar_intento("vale@ejemplo.com", "1.2.3.4", False)
        servicios.registrar_intento("vale@ejemplo.com", "1.2.3.4", True)
        servicios.registrar_intento("vale@ejemplo.com", "1.2.3.4", False)
        assert servicios.segundos_bloqueo("vale@ejemplo.com", "1.2.3.4") == 0

    def test_fallos_de_2fa_tambien_bloquean(self, client, dispositivo, settings):
        settings.ACCESO_MAX_FALLOS_EMAIL_IP = 2
        _entrar_con_password(client)
        client.post(VERIFICAR, {"codigo": "000000"})
        client.post(VERIFICAR, {"codigo": "111111"})
        r = client.post(VERIFICAR, {"codigo": codigo_totp(dispositivo)})
        assert "Demasiados intentos" in r.content.decode()
        assert not _esta_dentro(client)


class TestConfiguracion2FA:
    def test_alta_completa_y_codigos(self, client, usuaria):
        _entrar_con_password(client)
        r = client.get(CONFIGURAR)
        assert r.status_code == 200
        assert "<svg" in r.content.decode()  # QR generado en el servidor
        dispositivo = TOTPDevice.objects.get(user=usuaria, confirmed=False)
        r = client.post(CONFIGURAR, {"codigo": codigo_totp(dispositivo)})
        assert r["Location"] == reverse("cuentas:codigos")
        dispositivo.refresh_from_db()
        assert dispositivo.confirmed
        assert _esta_dentro(client)

        r = client.get(reverse("cuentas:codigos"))
        codigos = r.context["codigos"]
        assert len(codigos) == 8
        # Se guardan con hash, nunca en claro
        for fila in CodigoRecuperacion.objects.all():
            assert all(c.replace("-", "") not in fila.codigo_hash for c in codigos)
        # Solo se muestran una vez
        client.post(reverse("cuentas:codigos"))
        assert client.get(reverse("cuentas:codigos"))["Location"] == reverse("cuentas:cuenta")

    def test_codigo_invalido_no_activa(self, client, usuaria):
        _entrar_con_password(client)
        client.get(CONFIGURAR)
        client.post(CONFIGURAR, {"codigo": "123456"})
        assert not TOTPDevice.objects.filter(user=usuaria, confirmed=True).exists()
        assert not _esta_dentro(client)

    def test_sin_preauth_no_se_puede_configurar(self, client, usuaria):
        assert client.get(CONFIGURAR)["Location"] == LOGIN

    def test_reconfigurar_exige_codigo_actual(self, cliente_verificado, dispositivo):
        r = cliente_verificado.get(CONFIGURAR)
        assert r["Location"] == reverse("cuentas:cuenta")
        r = cliente_verificado.post(reverse("cuentas:cuenta"), {"accion": "reconfigurar", "codigo": "000000"})
        assert r.status_code == 200
        dispositivo.refresh_from_db()
        dispositivo.throttle_reset()  # django-otp impone una espera tras cada fallo
        r = cliente_verificado.post(
            reverse("cuentas:cuenta"), {"accion": "reconfigurar", "codigo": codigo_totp(dispositivo)}
        )
        assert r["Location"] == CONFIGURAR


class TestCodigosRecuperacion:
    def test_un_solo_uso(self, client, usuaria, dispositivo):
        codigos = servicios.generar_codigos_recuperacion(usuaria)
        _entrar_con_password(client)
        r = client.post(VERIFICAR + "?modo=recuperacion", {"codigo": codigos[0]})
        assert r.status_code == 302
        assert _esta_dentro(client)
        assert servicios.codigos_restantes(usuaria) == 7

        client.post(reverse("cuentas:salir"))
        _entrar_con_password(client)
        client.post(VERIFICAR + "?modo=recuperacion", {"codigo": codigos[0]})
        assert not _esta_dentro(client)

    def test_regenerar_invalida_los_anteriores(self, usuaria, dispositivo):
        viejos = servicios.generar_codigos_recuperacion(usuaria)
        servicios.generar_codigos_recuperacion(usuaria)
        disp = usuaria.dispositivorecuperacion_set.get()
        assert not disp.verify_token(viejos[0])

    def test_normalizacion(self):
        assert servicios.normalizar_codigo(" ABCDE-fghjk ") == "abcdefghjk"
        assert servicios.normalizar_codigo("corto") == ""
        assert servicios.normalizar_codigo("abcde-fgh0k") == ""  # 0 no está en el alfabeto


ALTA = reverse("cuentas:alta")
CODIGO = "codigo-de-alta-de-tests-0123456789"


def _datos_alta(**cambios):
    datos = {
        "email": "ayu@ejemplo.com",
        "nombre": "Ayu Pérez",
        "codigo_alta": CODIGO,
        "password1": "Clave-de-alta-larga-2026",
        "password2": "Clave-de-alta-larga-2026",
    }
    datos.update(cambios)
    return datos


class TestCorreosPermitidos:
    def test_correo_fuera_de_la_lista_no_entra_aunque_la_clave_sea_buena(self, client, settings, usuaria):
        settings.CORREOS_PERMITIDOS = ["otra@ejemplo.com"]
        r = _entrar_con_password(client)
        assert "Email o contraseña incorrectos" in r.content.decode()
        assert servicios.CLAVE_PREAUTH not in client.session
        assert RegistroAuditoria.objects.filter(descripcion__startswith="Correo no permitido").exists()

    def test_quitar_el_correo_corta_la_sesion_abierta(self, cliente_verificado, settings):
        assert _esta_dentro(cliente_verificado)
        settings.CORREOS_PERMITIDOS = []
        r = cliente_verificado.get("/")
        assert r.status_code == 302 and r["Location"].startswith(LOGIN)

    def test_preauth_caduca_si_sacan_el_correo(self, client, settings, usuaria, dispositivo):
        _entrar_con_password(client)
        settings.CORREOS_PERMITIDOS = []
        r = client.get(VERIFICAR)
        assert r.status_code == 302 and r["Location"] == LOGIN

    def test_lista_vacia_nadie_entra(self, client, settings, usuaria):
        settings.CORREOS_PERMITIDOS = []
        _entrar_con_password(client)
        assert servicios.CLAVE_PREAUTH not in client.session

    def test_mayusculas_y_espacios_da_igual(self, settings):
        from apps.cuentas.permitidos import esta_permitido

        settings.CORREOS_PERMITIDOS = [" Vale@Ejemplo.com "]
        assert esta_permitido("VALE@ejemplo.COM")
        assert not esta_permitido("")

    def test_crear_cuenta_rechaza_correo_no_permitido(self, monkeypatch):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        monkeypatch.setenv("CLAVE_PRUEBA", "Otra-clave-muy-larga-2026")
        with pytest.raises(CommandError, match="CORREOS_PERMITIDOS"):
            call_command("crear_cuenta", email="intrusa@ejemplo.com", password_env="CLAVE_PRUEBA")


class TestAlta:
    def test_alta_correcta_lleva_a_configurar_2fa(self, client):
        from apps.cuentas.models import Usuario

        r = client.post(ALTA, _datos_alta())
        assert r.status_code == 302 and r["Location"] == CONFIGURAR
        u = Usuario.objects.get(email="ayu@ejemplo.com")
        assert u.rol == Usuario.Rol.AYUDANTE  # no es el primero de la lista
        assert client.get(CONFIGURAR).status_code == 200
        assert not _esta_dentro(client)  # sin 2FA no hay sesión

    def test_primer_correo_de_la_lista_es_propietaria(self, client):
        from apps.cuentas.models import Usuario

        client.post(ALTA, _datos_alta(email="Vale@Ejemplo.com"))
        assert Usuario.objects.get(email="vale@ejemplo.com").es_propietaria

    @pytest.mark.parametrize(
        "cambios",
        [{"codigo_alta": "codigo-malo-0123456789"}, {"email": "intrusa@ejemplo.com"}],
    )
    def test_alta_rechazada_mismo_mensaje(self, client, cambios):
        from apps.cuentas.models import Usuario

        r = client.post(ALTA, _datos_alta(**cambios))
        assert "No se pudo crear la cuenta" in r.content.decode()
        assert not Usuario.objects.exists()
        assert IntentoAcceso.objects.filter(exito=False).count() == 1

    def test_no_se_puede_reclamar_una_cuenta_existente(self, client, usuaria):
        r = client.post(ALTA, _datos_alta(email="vale@ejemplo.com"))
        assert "No se pudo crear la cuenta" in r.content.decode()
        usuaria.refresh_from_db()
        assert usuaria.check_password(CLAVE)

    def test_clave_debil(self, client):
        from apps.cuentas.models import Usuario

        r = client.post(ALTA, _datos_alta(password1="corta", password2="corta"))
        assert r.status_code == 200
        assert not Usuario.objects.exists()

    def test_sin_codigo_configurado_no_existe(self, client, settings):
        settings.CODIGO_ALTA = ""
        assert client.get(ALTA).status_code == 404
        assert "Crea tu cuenta" not in client.get(LOGIN).content.decode()

    def test_alta_respeta_el_bloqueo(self, client, settings):
        settings.ACCESO_MAX_FALLOS_EMAIL_IP = 2
        for _ in range(2):
            client.post(ALTA, _datos_alta(codigo_alta="codigo-malo-0123456789"))
        r = client.post(ALTA, _datos_alta())
        assert "Demasiados intentos" in r.content.decode()


class TestChecks:
    def test_avisos(self, settings):
        from apps.cuentas.checks import revisar_acceso

        settings.CORREOS_PERMITIDOS = []
        settings.CODIGO_ALTA = "corto"
        ids = {a.id for a in revisar_acceso(None)}
        assert ids == {"cuentas.W001", "cuentas.E001"}
