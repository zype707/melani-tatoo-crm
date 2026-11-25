import time

import pytest
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.cuentas.models import Usuario

CLAVE = "Una-clave-larga-de-pruebas-2026"


@pytest.fixture
def usuaria(db):
    return Usuario.objects.create_user(email="vale@ejemplo.com", password=CLAVE, nombre="Vale Ríos")


@pytest.fixture
def dispositivo(usuaria):
    return TOTPDevice.objects.create(user=usuaria, name="App", confirmed=True)


def codigo_totp(dispositivo) -> str:
    dispositivo.refresh_from_db()
    while int(time.time()) // dispositivo.step <= dispositivo.last_t:
        time.sleep(0.5)
    return f"{totp(dispositivo.bin_key, step=dispositivo.step, digits=dispositivo.digits):06d}"


@pytest.fixture
def cliente_verificado(client, usuaria, dispositivo):
    """Cliente HTTP con sesión iniciada y segundo factor verificado."""
    client.force_login(usuaria)
    sesion = client.session
    sesion["otp_device_id"] = dispositivo.persistent_id
    sesion.save()
    return client


@pytest.fixture
def htmx():
    return {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def cache_limpia():
    """Los límites de peticiones viven en la caché: cada test empieza de cero."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
