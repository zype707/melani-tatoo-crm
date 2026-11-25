import io
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.clientes.models import Cliente, DatosSalud
from apps.cuentas.models import Usuario
from apps.nucleo.exportacion import copia_de_seguridad

pytestmark = pytest.mark.django_db(transaction=True)


def test_copia_y_restauracion_completa(usuaria, dispositivo):
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
    assert Usuario.objects.filter(email=usuaria.email).exists()
    assert TOTPDevice.objects.filter(user__email=usuaria.email, confirmed=True).exists()
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
