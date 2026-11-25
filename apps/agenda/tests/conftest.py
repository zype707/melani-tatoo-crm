from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.agenda.models import Cita, HorarioLaboral, TipoCita
from apps.clientes.models import Cliente


def momento(dias: int, hora: int, minuto: int = 0):
    fecha = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(fecha, time(hora, minuto)))


@pytest.fixture
def sesion(db):
    return TipoCita.objects.create(nombre="Sesión", categoria="sesion", duracion_minutos=180, deposito_sugerido=100)


@pytest.fixture
def consulta(db):
    return TipoCita.objects.create(nombre="Consulta", categoria="consulta", duracion_minutos=30)


@pytest.fixture
def horario(db):
    for d in range(7):
        HorarioLaboral.objects.create(dia_semana=d, hora_inicio=time(9), hora_fin=time(20))


@pytest.fixture
def lucia(db):
    return Cliente.objects.create(nombre="Lucía", apellidos="Méndez", telefono="+14075550123")


@pytest.fixture
def marcus(db):
    return Cliente.objects.create(nombre="Marcus", apellidos="Reed", telefono="+14075550145")


@pytest.fixture
def cita(lucia, sesion):
    return Cita.objects.create(cliente=lucia, tipo=sesion, inicio=momento(2, 12), fin=momento(2, 15))
