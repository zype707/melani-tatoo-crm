import io
import json
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.clientes.models import Cliente, DatosSalud
from apps.cuentas.models import Usuario
from apps.nucleo.exportacion import copia_de_seguridad
from conftest import CLAVE

pytestmark = pytest.mark.django_db(transaction=True)


def test_copia_y_restauracion_completa(usuaria):
    c = Cliente.objects.create(nombre="Rosa", apellidos="Copia", telefono="+14075550111")
    DatosSalud.objects.create(cliente=c, alergias="Níquel")
    archivo = Path(settings.MEDIA_ROOT) / "fotos" / "prueba.jpg"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_bytes(b"\xff\xd8\xffcontenido")
    copia = copia_de_seguridad()

    # Desastre: se pierde todo
    Cliente.objects.all().delete()
    Usuario.objects.all().delete()
    archivo.unlink()

    call_command("restaurar_copia", str(copia), "--si", stdout=io.StringIO())
    restaurada = Cliente.objects.get(apellidos="Copia")
    assert restaurada.salud.alergias == "Níquel"
    assert Usuario.objects.get(usuario=usuaria.usuario).check_password(CLAVE)
    assert archivo.read_bytes().endswith(b"contenido")


def test_no_pisa_datos_sin_sobrescribir(tmp_path):
    Cliente.objects.create(nombre="Ya", apellidos="Existe", telefono="+14075550112")
    copia = copia_de_seguridad()
    with pytest.raises(CommandError, match="sobrescribir"):
        call_command("restaurar_copia", str(copia), "--si")


def test_rechaza_zip_con_rutas_peligrosas(tmp_path):
    malo = tmp_path / "malo.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("datos.json", "[]")
        z.writestr("archivos/../../fuera.txt", "x")
    with pytest.raises(CommandError, match="sospechosa"):
        call_command("restaurar_copia", str(malo), "--si")


def test_restaura_copias_anteriores_al_acceso_por_usuario(tmp_path):
    """Las copias de antes traían 2FA y el email como identificador: se adaptan al restaurar."""
    antigua = tmp_path / "copia-antigua.zip"
    datos = [
        {
            "model": "cuentas.usuario",
            "pk": 1,
            "fields": {
                "password": "md5$x$hash",
                "last_login": None,
                "is_superuser": False,
                "email": "vale@ejemplo.com",
                "nombre": "Vale",
                "rol": "propietaria",
                "is_active": True,
                "is_staff": False,
                "fecha_alta": "2026-01-01T00:00:00Z",
                "groups": [],
                "user_permissions": [],
            },
        },
        {"model": "otp_totp.totpdevice", "pk": 1, "fields": {"user": 1, "name": "App", "key": "abc"}},
        {"model": "cuentas.dispositivorecuperacion", "pk": 1, "fields": {"user": 1, "name": "Códigos"}},
        {
            "model": "cuentas.intentoacceso",
            "pk": 1,
            "fields": {
                "email": "vale@ejemplo.com",
                "ip": None,
                "exito": True,
                "fase": "2fa",
                "creado_en": "2026-01-01T00:00:00Z",
            },
        },
    ]
    with zipfile.ZipFile(antigua, "w") as z:
        z.writestr("datos.json", json.dumps(datos))
    call_command("restaurar_copia", str(antigua), "--si", stdout=io.StringIO())
    u = Usuario.objects.get()
    assert u.usuario == "vale" and u.password == "md5$x$hash"
