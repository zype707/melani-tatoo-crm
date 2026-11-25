from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.agenda.models import Cita, TipoCita
from apps.clientes.models import Cliente
from apps.finanzas.models import Pago
from apps.mensajeria.models import MensajePreparado

pytestmark = pytest.mark.django_db


def test_panel_con_datos(cliente_verificado):
    tipo = TipoCita.objects.create(nombre="Sesión", duracion_minutos=120)
    c = Cliente.objects.create(nombre="Ana", apellidos="Prueba", telefono="+14075550101")
    inicio = timezone.now() + timedelta(hours=2)
    Cita.objects.create(cliente=c, tipo=tipo, inicio=inicio, fin=inicio + timedelta(hours=2), estado="confirmada")
    Pago.objects.create(cliente=c, tipo="sesion", importe=300, fecha=timezone.localdate(), metodo="efectivo")
    r = cliente_verificado.get("/")
    assert r.status_code == 200
    contenido = r.content.decode()
    assert "Ana" in contenido
    assert "$300" in contenido
    assert "<svg" in contenido  # gráfico propio, sin librerías


def test_panel_vacio(cliente_verificado):
    r = cliente_verificado.get("/")
    assert r.status_code == 200


def test_seed_demo_crea_estudio_coherente(settings):
    settings.SITE_URL = "https://estudio.test"
    call_command("seed_demo", "--forzar", stdout=StringIO())
    assert Cliente.objects.count() == 40
    assert Cita.objects.filter(inicio__gt=timezone.now()).exists()
    assert MensajePreparado.objects.pendientes().exists()
    # Ningún teléfono fuera del rango ficticio 555-01XX
    assert all(t[5:9] == "5550" for t in Cliente.objects.values_list("telefono", flat=True))
    # Volver a ejecutarlo sin --limpiar no duplica datos
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_demo", "--forzar")
