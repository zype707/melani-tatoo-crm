"""La migración 0002 pasa las cuentas existentes del acceso por email al acceso por usuario."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

ANTES = [("cuentas", "0001_initial")]
DESPUES = [("cuentas", "0002_acceso_por_usuario")]


def _migrar(destino):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(destino)
    return executor.loader.project_state(destino).apps


def test_email_pasa_a_usuario_y_conserva_la_contrasena():
    try:
        apps_antes = _migrar(ANTES)
        Usuario = apps_antes.get_model("cuentas", "Usuario")
        Usuario.objects.create(email="vale@ejemplo.com", nombre="Vale", password="md5$x$hash-de-vale")
        Usuario.objects.create(email="Vale@otro.com", nombre="Vale 2", password="md5$x$hash-2")
        Usuario.objects.create(email="ayu@ejemplo.com", nombre="Ayu", rol="ayudante", password="md5$x$hash-3")

        apps_despues = _migrar(DESPUES)
        Usuario = apps_despues.get_model("cuentas", "Usuario")
        cuentas = {u.nombre: u for u in Usuario.objects.all()}
        assert cuentas["Vale"].usuario == "vale"
        assert cuentas["Vale 2"].usuario == "vale2"
        assert cuentas["Ayu"].usuario == "ayu" and cuentas["Ayu"].rol == "ayudante"
        assert cuentas["Vale"].password == "md5$x$hash-de-vale"
        with connection.cursor() as cursor:
            tablas = connection.introspection.table_names(cursor)
        assert "cuentas_codigorecuperacion" not in tablas and "otp_totp_totpdevice" not in tablas
    finally:
        _migrar(MigrationExecutor(connection).loader.graph.leaf_nodes())
