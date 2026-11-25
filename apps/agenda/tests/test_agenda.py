from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicios
from apps.agenda.forms import CitaForm
from apps.agenda.models import Bloqueo, Cita, EntradaListaEspera, EstadoCita
from apps.clientes.models import Cliente, NotaCliente
from apps.finanzas.models import Pago
from apps.nucleo import tokens

from .conftest import momento

pytestmark = pytest.mark.django_db


def datos_cita(cliente, tipo, dias=2, hora="12:00", duracion=180, **extra):
    fecha = (timezone.localdate() + timedelta(days=dias)).isoformat()
    return {
        "cliente": cliente.pk,
        "tipo": tipo.pk,
        "estado": "confirmada",
        "fecha": fecha,
        "hora": hora,
        "duracion": duracion,
        **extra,
    }


class TestSolapes:
    def test_restriccion_en_base_de_datos(self, cita, marcus, sesion):
        with pytest.raises(IntegrityError), transaction.atomic():
            Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 14), fin=momento(2, 16))

    def test_citas_contiguas_permitidas(self, cita, marcus, sesion):
        Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 15), fin=momento(2, 16))
        Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 11), fin=momento(2, 12))
        assert Cita.objects.count() == 3

    def test_cancelada_libera_el_hueco(self, cita, marcus, sesion):
        servicios.cambiar_estado(cita, EstadoCita.CANCELADA)
        Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 12), fin=momento(2, 15))

    def test_no_show_libera_el_hueco(self, cita, marcus, sesion):
        servicios.cambiar_estado(cita, EstadoCita.NO_SHOW)
        Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 13), fin=momento(2, 14))

    def test_reactivar_sobre_hueco_ocupado_falla(self, cita, marcus, sesion):
        servicios.cambiar_estado(cita, EstadoCita.CANCELADA)
        Cita.objects.create(cliente=marcus, tipo=sesion, inicio=momento(2, 12), fin=momento(2, 13))
        with pytest.raises(servicios.ConflictoAgenda):
            servicios.cambiar_estado(cita, EstadoCita.CONFIRMADA)

    def test_formulario_rechaza_solape(self, cita, marcus, sesion, horario):
        form = CitaForm(datos_cita(marcus, sesion, hora="13:00", duracion=60))
        assert not form.is_valid()
        assert "Se solapa" in str(form.non_field_errors())

    def test_formulario_permite_editar_la_misma_cita(self, cita, lucia, sesion, horario):
        form = CitaForm(datos_cita(lucia, sesion, hora="12:30"), instance=cita)
        assert form.is_valid(), form.errors

    def test_bloqueo_impide_cita(self, marcus, sesion, horario):
        Bloqueo.objects.create(inicio=momento(3, 0), fin=momento(4, 0), motivo="Vacaciones")
        form = CitaForm(datos_cita(marcus, sesion, dias=3))
        assert not form.is_valid()
        assert "bloqueado" in str(form.non_field_errors())

    def test_fuera_de_horario_pide_confirmacion(self, marcus, consulta, horario):
        form = CitaForm(datos_cita(marcus, consulta, hora="21:00", duracion=30))
        assert not form.is_valid()
        assert "fuera_de_horario" in form.errors
        form = CitaForm(datos_cita(marcus, consulta, hora="21:00", duracion=30, fuera_de_horario="on"))
        assert form.is_valid(), form.errors

    def test_vista_crea_cita_y_cliente_rapido(self, cliente_verificado, sesion, horario):
        datos = datos_cita(Cliente(pk=0), sesion)
        datos.update(cliente="", nuevo_cliente_nombre="Ana Nueva", nuevo_cliente_telefono="407 555 0177")
        r = cliente_verificado.post(reverse("agenda:nueva"), datos)
        assert r.status_code == 302
        ana = Cliente.objects.get(nombre="Ana Nueva")
        assert ana.telefono == "+14075550177"
        assert ana.citas.count() == 1

    def test_vista_muestra_error_si_el_hueco_se_ocupa_a_la_vez(
        self, cliente_verificado, cita, marcus, sesion, horario, monkeypatch
    ):
        # Simula la carrera: la validación no ve el solape, pero la BD lo impide.
        monkeypatch.setattr(servicios, "conflictos", lambda *a, **k: [])
        r = cliente_verificado.post(reverse("agenda:nueva"), datos_cita(marcus, sesion, hora="13:00", duracion=60))
        assert r.status_code == 200
        assert "acaba de ocuparse" in r.content.decode()
        assert Cita.objects.count() == 1


class TestDisponibilidad:
    def test_huecos_libres(self, cita, horario):
        huecos = servicios.huecos_libres(timezone.localdate() + timedelta(days=2), dias=1, minimo_minutos=60)
        tramos = [(timezone.localtime(h["inicio"]).hour, timezone.localtime(h["fin"]).hour) for h in huecos]
        assert tramos == [(9, 12), (15, 20)]

    def test_fuera_de_horario(self, horario):
        assert not servicios.fuera_de_horario(momento(1, 10), momento(1, 12))
        assert servicios.fuera_de_horario(momento(1, 19), momento(1, 21))


class TestListaEspera:
    def test_sugerencias_respetan_dia_y_franja(self, cita, marcus, sesion):
        dia = timezone.localtime(cita.inicio).weekday()
        bien = EntradaListaEspera.objects.create(cliente=marcus, dias=[dia], franja="manana")
        otra = Cliente.objects.create(nombre="Otra", telefono="+14075550100")
        EntradaListaEspera.objects.create(cliente=otra, dias=[(dia + 1) % 7])
        tarde = Cliente.objects.create(nombre="Tarde", telefono="+14075550101")
        EntradaListaEspera.objects.create(cliente=tarde, franja="tarde")
        servicios.cambiar_estado(cita, EstadoCita.CANCELADA)
        assert servicios.sugerencias_lista_espera(cita) == [bien]

    def test_prioritaria_primero(self, cita, marcus):
        normal = EntradaListaEspera.objects.create(cliente=marcus)
        vip = Cliente.objects.create(nombre="Vip", telefono="+14075550102")
        prioritaria = EntradaListaEspera.objects.create(cliente=vip, prioritaria=True)
        assert servicios.sugerencias_lista_espera(cita) == [prioritaria, normal]


class TestVistas:
    @pytest.mark.parametrize("vista", ["dia", "semana", "mes", "lista"])
    def test_calendario(self, cliente_verificado, cita, horario, vista):
        fecha = timezone.localtime(cita.inicio).date().isoformat()
        r = cliente_verificado.get(reverse("agenda:calendario"), {"vista": vista, "fecha": fecha})
        assert r.status_code == 200
        assert "Lucía" in r.content.decode()

    def test_cerrar_sesion_registra_pago_nota_y_estado(self, cliente_verificado, cita):
        r = cliente_verificado.post(
            reverse("agenda:cerrar_sesion", args=[cita.pk]),
            {"importe": "350", "metodo": "zelle", "notas_sesion": "Piel reactiva en la zona interna"},
        )
        assert r.status_code == 302
        cita.refresh_from_db()
        assert cita.estado == EstadoCita.REALIZADA
        assert Pago.objects.get(cita=cita).importe == 350
        assert NotaCliente.objects.filter(cita=cita, origen="sesion").exists()

    def test_registrar_sena(self, cliente_verificado, cita):
        cliente_verificado.post(
            reverse("agenda:pago_nuevo", args=[cita.pk]),
            {"tipo": "sena", "importe": "100", "metodo": "venmo", "fecha": timezone.localdate().isoformat()},
        )
        assert cita.pagado == 100

    def test_vistas_privadas(self, client, cita):
        assert client.get(reverse("agenda:detalle", args=[cita.pk])).status_code == 302


class TestPaginaPublicaCita:
    def _url(self, cita):
        return servicios.enlace_cita(cita).replace("https://estudio.test", "")

    def test_ver_y_confirmar(self, client, cita):
        cita.estado = EstadoCita.SOLICITADA
        cita.save()
        url = self._url(cita)
        r = client.get(url)
        assert r.status_code == 200
        assert "Lucía" in r.content.decode()
        assert "Méndez" not in r.content.decode()  # mínimo de datos personales
        client.post(url, {"accion": "confirmar"})
        cita.refresh_from_db()
        assert cita.estado == EstadoCita.CONFIRMADA
        assert cita.confirmada_cliente_en is not None

    def test_cancelar(self, client, cita):
        client.post(self._url(cita), {"accion": "cancelar", "motivo": "Viaje"})
        cita.refresh_from_db()
        assert cita.estado == EstadoCita.CANCELADA
        assert cita.cancelada_por == "cliente"

    def test_pedir_reprogramacion(self, client, cita):
        client.post(self._url(cita), {"accion": "reprogramar", "texto": "Mejor el sábado"})
        cita.refresh_from_db()
        assert cita.reprogramacion_pedida == "Mejor el sábado"
        assert cita.requiere_atencion

    def test_token_invalido(self, client, cita):
        assert client.get("/c/" + "x" * 43 + "/").status_code == 404

    def test_token_caducado(self, client, cita):
        url = self._url(cita)
        tokens.EnlacePublico.objects.update(caduca_en=timezone.now() - timedelta(minutes=1))
        assert client.get(url).status_code == 404

    def test_token_revocado(self, client, cita):
        url = self._url(cita)
        tokens.revocar("cita", cita.pk)
        assert client.get(url).status_code == 404

    def test_cita_pasada_no_se_puede_cancelar(self, client, lucia, sesion):
        pasada = Cita.objects.create(cliente=lucia, tipo=sesion, inicio=momento(-1, 12), fin=momento(-1, 13))
        client.post(self._url(pasada), {"accion": "cancelar"})
        pasada.refresh_from_db()
        assert pasada.estado == EstadoCita.CONFIRMADA

    def test_limite_de_peticiones(self, client, cita):
        url = self._url(cita)
        for _ in range(20):
            client.post(url, {"accion": "nada"})
        assert client.post(url, {"accion": "nada"}).status_code == 429
