import pytest

from apps.cuentas.models import Usuario

CLAVE = "Una-clave-larga-de-pruebas-2026"


@pytest.fixture
def usuaria(db):
    return Usuario.objects.create_user(usuario="vale", password=CLAVE, nombre="Vale Ríos")


@pytest.fixture
def cliente_verificado(client, usuaria):
    """Cliente HTTP con sesión iniciada (propietaria)."""
    client.force_login(usuaria)
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
