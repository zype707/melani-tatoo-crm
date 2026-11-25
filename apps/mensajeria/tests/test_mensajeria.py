from datetime import date, datetime, time, timedelta
from urllib.parse import unquote

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Cita, EstadoCita, TipoCita
from apps.clientes.models import Cliente, Tatuaje
from apps.mensajeria import canales, generadores, servicios, variables
from apps.mensajeria.models import Campana, Categoria, FechaDestacada, MensajePreparado, Plantilla
from apps.mensajeria.predeterminados import crear_predeterminados
from apps.nucleo import tokens

pytestmark = pytest.mark.django_db
Estado = MensajePreparado.Estado


def hoy():
    return timezone.localdate()


def momento(dias, hora=12):
    return timezone.make_aware(datetime.combine(hoy() + timedelta(days=dias), time(hora)))


@pytest.fixture
def estudio(db):
    crear_predeterminados()


@pytest.fixture
def sesion(estudio):
    return TipoCita.objects.get(categoria="sesion", nombre="Sesión")


def cliente(nombre="Ana", consentimiento=False, **extra):
    c = Cliente.objects.create(nombre=nombre, telefono=extra.pop("telefono", "+14075550123"), **extra)
    if consentimiento:
        c.dar_consentimiento("presencial")
    return c


def cita_realizada(c, tipo, dias_atras, tatuaje=None):
    return Cita.objects.create(
        cliente=c,
        tipo=tipo,
        tatuaje=tatuaje,
        inicio=momento(-dias_atras),
        fin=momento(-dias_atras, 15),
        estado=EstadoCita.REALIZADA,
    )


class TestCanales:
    def test_whatsapp_codifica_el_texto(self):
        c = Cliente(nombre="Ana", telefono="+14075550123")
        accion = canales.REGISTRO["whatsapp_link"].accion(c, "¡Hola Ana!\nMañana a las 3 & 4 #ok")
        assert accion.url.startswith("https://wa.me/14075550123?text=")
        cola = accion.url.split("text=")[1]
        assert " " not in cola and "\n" not in cola and "&" not in cola and "#" not in cola
        assert unquote(cola) == "¡Hola Ana!\nMañana a las 3 & 4 #ok"

    def test_sms(self):
        c = Cliente(nombre="Ana", telefono="+14075550123")
        assert canales.REGISTRO["sms_link"].accion(c, "Hola").url == "sms:+14075550123?&body=Hola"

    def test_orden_por_preferencia(self):
        c = Cliente(nombre="Ana", telefono="+14075550123", canal_preferido="sms")
        acciones = canales.acciones_para(c, "x")
        assert [a.canal for a in acciones] == ["sms_link", "whatsapp_link", "copia"]
        assert acciones[0].principal

    def test_sin_telefono_solo_copiar(self):
        c = Cliente(nombre="Ana", instagram="ana")
        assert [a.canal for a in canales.acciones_para(c, "x")] == ["copia"]


class TestVariables:
    def test_renderizar(self):
        assert variables.renderizar("Hola {nombre}, {desconocida}", {"nombre": "Ana"}) == "Hola Ana, {desconocida}"

    def test_desconocidas(self):
        assert variables.desconocidas("{nombre} {nombr} {fecha_cita} {x}") == ["nombr", "x"]


class TestIdempotencia:
    def test_ejecutar_dos_veces_no_duplica(self, sesion):
        c = cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1990))
        Cita.objects.create(cliente=c, tipo=sesion, inicio=momento(1), fin=momento(1, 15))
        cita_realizada(cliente("Bea", telefono="+14075550124"), sesion, 1)
        primero = generadores.ejecutar_diario()
        total = MensajePreparado.objects.count()
        assert total >= 3
        segundo = generadores.ejecutar_diario()
        assert MensajePreparado.objects.count() == total
        assert all(segundo[k] == 0 for k in generadores.GENERADORES)
        assert primero["recordatorios"] == 1

    def test_comando_diario_dos_veces(self, sesion):
        cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1985))
        call_command("tareas_diarias")
        call_command("tareas_diarias")
        assert MensajePreparado.objects.filter(tipo=Categoria.CUMPLEANOS).count() == 1

    def test_descartado_no_reaparece(self, sesion):
        cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1985))
        generadores.ejecutar_diario()
        servicios.descartar(MensajePreparado.objects.get())
        generadores.ejecutar_diario()
        assert MensajePreparado.objects.count() == 1


class TestConsentimiento:
    def test_cumpleanos_requiere_consentimiento(self, estudio):
        cliente("Sin", fecha_nacimiento=hoy().replace(year=1990))
        cliente("Con", consentimiento=True, telefono="+14075550125", fecha_nacimiento=hoy().replace(year=1990))
        generadores.generar_cumpleanos(hoy())
        assert list(MensajePreparado.objects.values_list("cliente__nombre", flat=True)) == ["Con"]

    def test_servicio_no_requiere_consentimiento(self, sesion):
        c = cliente()  # sin consentimiento de marketing
        Cita.objects.create(cliente=c, tipo=sesion, inicio=momento(1), fin=momento(1, 15))
        assert generadores.generar_recordatorios(hoy()) == 1

    def test_no_contactar_bloquea_todo(self, sesion):
        c = cliente(consentimiento=True, contacto_bloqueado=True, fecha_nacimiento=hoy().replace(year=1990))
        Cita.objects.create(cliente=c, tipo=sesion, inicio=momento(1), fin=momento(1, 15))
        generadores.ejecutar_diario()
        assert not MensajePreparado.objects.exists()

    def test_baja_posterior_oculta_y_bloquea_envio(self, estudio):
        c = cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1990))
        generadores.generar_cumpleanos(hoy())
        m = MensajePreparado.objects.get()
        assert m in servicios.bandeja()
        c.retirar_consentimiento("peticion_baja")
        assert m not in servicios.bandeja()
        with pytest.raises(servicios.EnvioNoPermitido):
            servicios.marcar_enviado(m, "whatsapp_link")

    def test_baja_desde_ficha_descarta_pendientes(self, cliente_verificado, estudio):
        c = cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1990))
        generadores.generar_cumpleanos(hoy())
        cliente_verificado.post(
            reverse("clientes:marketing", args=[c.pk]), {"accion": "baja", "origen": "peticion_baja"}
        )
        assert MensajePreparado.objects.get().estado == Estado.DESCARTADO

    def test_limpieza_diaria_descarta_promos_sin_consentimiento(self, estudio):
        c = cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1990))
        generadores.generar_cumpleanos(hoy())
        c.marketing_consentimiento = False
        c.save()
        generadores.ejecutar_diario()
        assert MensajePreparado.objects.get().estado == Estado.DESCARTADO

    def test_campana_solo_con_consentimiento(self, estudio):
        cliente("Sin")
        cliente("Con", consentimiento=True, telefono="+14075550126")
        campana = Campana.objects.create(
            nombre="Flash", plantilla=Plantilla.para(Categoria.CAMPANA), segmento="marketing"
        )
        assert generadores.lanzar_campana(campana) == 1
        assert MensajePreparado.objects.get().cliente.nombre == "Con"


class TestRecordatorios:
    def test_incluye_enlace_valido(self, sesion):
        c = cliente()
        cita = Cita.objects.create(cliente=c, tipo=sesion, inicio=momento(1), fin=momento(1, 15))
        generadores.generar_recordatorios(hoy())
        m = MensajePreparado.objects.get()
        token = m.texto.split("/c/")[1].split("/")[0]
        assert tokens.resolver("cita", token).objeto_id == cita.pk

    def test_reprogramar_genera_nuevo_recordatorio(self, sesion):
        cita = Cita.objects.create(cliente=cliente(), tipo=sesion, inicio=momento(1), fin=momento(1, 15))
        generadores.generar_recordatorios(hoy())
        cita.inicio, cita.fin = momento(1, 16), momento(1, 18)
        cita.save()
        generadores.generar_recordatorios(hoy())
        assert MensajePreparado.objects.filter(tipo=Categoria.RECORDATORIO).count() == 2

    def test_cancelada_sin_recordatorio(self, sesion):
        Cita.objects.create(
            cliente=cliente(), tipo=sesion, inicio=momento(1), fin=momento(1, 15), estado=EstadoCita.CANCELADA
        )
        assert generadores.generar_recordatorios(hoy()) == 0


class TestCuidados:
    def test_toca_el_paso_del_dia_sin_acumular(self, sesion):
        cita_realizada(cliente(), sesion, 3)
        generadores.generar_cuidados(hoy())
        motivos = list(MensajePreparado.objects.values_list("motivo", flat=True))
        assert len(motivos) == 1 and motivos[0].startswith("Día 3")

    def test_recupera_si_el_cron_fallo_un_dia(self, sesion):
        cita_realizada(cliente(), sesion, 2)  # el día 1 tocaba ayer
        generadores.generar_cuidados(hoy())
        assert MensajePreparado.objects.get().motivo.startswith("Día 1")

    def test_consulta_no_genera_cuidados(self, estudio):
        consulta = TipoCita.objects.get(categoria="consulta")
        cita_realizada(cliente(), consulta, 1)
        assert generadores.generar_cuidados(hoy()) == 0

    def test_oferta_de_retoque(self, sesion):
        c = cliente()
        t = Tatuaje.objects.create(cliente=c, titulo="Rosa", estado="terminado")
        cita_realizada(c, sesion, 30, tatuaje=t)
        generadores.generar_cuidados(hoy())
        assert MensajePreparado.objects.get().tipo == Categoria.RETOQUE

    def test_sin_retoque_si_quedan_sesiones(self, sesion):
        c = cliente()
        t = Tatuaje.objects.create(cliente=c, titulo="Manga")
        cita_realizada(c, sesion, 30, tatuaje=t)
        Cita.objects.create(cliente=c, tipo=sesion, tatuaje=t, inicio=momento(5), fin=momento(5, 15))
        generadores.generar_cuidados(hoy())
        assert not MensajePreparado.objects.filter(tipo=Categoria.RETOQUE).exists()

    def test_sin_retoque_si_ya_se_hizo(self, sesion):
        c = cliente()
        t = Tatuaje.objects.create(cliente=c, titulo="Rosa", retoque_hecho=True)
        cita_realizada(c, sesion, 30, tatuaje=t)
        assert generadores.generar_cuidados(hoy()) == 0


class TestAniversariosYReactivacion:
    def test_aniversario(self, estudio):
        c = cliente(consentimiento=True)
        hace_un_anio = hoy().replace(year=hoy().year - 1)
        Tatuaje.objects.create(cliente=c, titulo="Golondrina", estado="terminado", fecha_fin=hace_un_anio)
        generadores.generar_aniversarios(hoy())
        m = MensajePreparado.objects.get()
        assert "1 año" in m.texto and "Golondrina" in m.texto

    def test_reactivacion_con_cupo(self, sesion):
        for i in range(5):
            c = cliente(f"C{i}", consentimiento=True, telefono=f"+1407555013{i}")
            cita_realizada(c, sesion, 300 + i)
        assert generadores.generar_reactivaciones(hoy()) == 3  # cupo por defecto
        assert generadores.generar_reactivaciones(hoy()) == 0  # mismo día: no rellena

    def test_reactivacion_omite_clientes_con_cita_futura(self, sesion):
        c = cliente(consentimiento=True)
        cita_realizada(c, sesion, 300)
        Cita.objects.create(cliente=c, tipo=sesion, inicio=momento(3), fin=momento(3, 15))
        assert generadores.generar_reactivaciones(hoy()) == 0


class TestFechasYCampanas:
    def test_fecha_destacada_reparte_en_la_ventana(self, estudio):
        for i in range(6):
            cliente(f"C{i}", consentimiento=True, telefono=f"+1407555014{i}")
        dentro_de_dos = hoy() + timedelta(days=2)
        FechaDestacada.objects.create(
            nombre="Prueba",
            regla="unica",
            fecha=dentro_de_dos,
            dias_ventana=3,
            plantilla=Plantilla.para(Categoria.FECHA_DESTACADA),
        )
        assert generadores.generar_fechas_destacadas(hoy()) == 6
        fechas = sorted(MensajePreparado.objects.values_list("fecha_programada", flat=True))
        assert fechas[0] == hoy() and fechas[-1] == dentro_de_dos
        assert len(set(fechas)) == 3
        assert generadores.generar_fechas_destacadas(hoy()) == 0  # idempotente

    def test_campana_escalonada(self, estudio):
        for i in range(25):
            cliente(f"C{i}", consentimiento=True, telefono=f"+14075551{i:03d}")
        campana = Campana.objects.create(
            nombre="Flash", plantilla=Plantilla.para(Categoria.CAMPANA), segmento="marketing", por_dia=10
        )
        generadores.lanzar_campana(campana)
        por_dia = {}
        for f in MensajePreparado.objects.values_list("fecha_programada", flat=True):
            por_dia[f] = por_dia.get(f, 0) + 1
        assert sorted(por_dia.values(), reverse=True) == [10, 10, 5]
        assert generadores.lanzar_campana(campana) == 0

    @pytest.mark.parametrize(
        ("regla", "esperado"),
        [
            ({"regla": "nth", "mes": 5, "semana": 2, "dia_semana": 6}, date(2026, 5, 10)),
            ({"regla": "nth", "mes": 11, "semana": 4, "dia_semana": 3}, date(2026, 11, 26)),
            ({"regla": "ultimo", "mes": 5, "dia_semana": 0}, date(2026, 5, 25)),
            ({"regla": "fija", "mes": 2, "dia": 29}, date(2026, 2, 28)),
        ],
    )
    def test_reglas_de_fechas(self, regla, esperado):
        assert FechaDestacada(nombre="x", **regla).fecha_en(2026) == esperado

    def test_viernes_13(self):
        assert FechaDestacada(nombre="x", regla="viernes13").proxima(date(2026, 1, 1)) == date(2026, 2, 13)


class TestVistasBandeja:
    @pytest.fixture
    def mensaje(self, estudio):
        c = cliente(consentimiento=True, fecha_nacimiento=hoy().replace(year=1990))
        generadores.generar_cumpleanos(hoy())
        return MensajePreparado.objects.get(cliente=c)

    def test_bandeja(self, cliente_verificado, mensaje):
        r = cliente_verificado.get(reverse("mensajeria:bandeja"))
        assert r.status_code == 200
        assert "https://wa.me/14075550123?text=" in r.content.decode()

    def test_abrir_guarda_texto_y_pregunta(self, cliente_verificado, mensaje, htmx):
        r = cliente_verificado.post(
            reverse("mensajeria:abrir", args=[mensaje.pk]), {"canal": "whatsapp_link", "texto": "Texto editado"}, **htmx
        )
        assert "¿Lo enviaste" in r.content.decode()
        mensaje.refresh_from_db()
        assert mensaje.texto == "Texto editado" and mensaje.canal_usado == "whatsapp_link"

    def test_marcar_enviado_queda_en_historial(self, cliente_verificado, mensaje, htmx):
        cliente_verificado.post(reverse("mensajeria:enviado", args=[mensaje.pk]), {"canal": "sms_link"}, **htmx)
        mensaje.refresh_from_db()
        assert mensaje.estado == Estado.ENVIADO and mensaje.canal_usado == "sms_link"
        r = cliente_verificado.get(reverse("mensajeria:historial"))
        assert mensaje.cliente.nombre in r.content.decode()
        r = cliente_verificado.get(reverse("clientes:ficha", args=[mensaje.cliente.pk]))
        assert "Mensaje enviado" in r.content.decode()

    def test_posponer_y_descartar(self, cliente_verificado, mensaje, htmx):
        cliente_verificado.post(reverse("mensajeria:posponer", args=[mensaje.pk]), {"dias": "3"}, **htmx)
        mensaje.refresh_from_db()
        assert mensaje.fecha_programada == hoy() + timedelta(days=3)
        assert mensaje not in servicios.bandeja()
        cliente_verificado.post(reverse("mensajeria:descartar", args=[mensaje.pk]), **htmx)
        mensaje.refresh_from_db()
        assert mensaje.estado == Estado.DESCARTADO

    def test_plantilla_con_variable_inexistente(self, cliente_verificado, estudio):
        r = cliente_verificado.post(
            reverse("mensajeria:plantilla_nueva"),
            {"nombre": "X", "categoria": "general", "cuerpo": "Hola {nonbre}", "activa": "on"},
        )
        assert r.status_code == 200
        assert "Variables que no existen" in r.content.decode()

    def test_mensaje_libre(self, cliente_verificado, estudio):
        c = cliente()
        r = cliente_verificado.post(reverse("mensajeria:nuevo"), {"cliente": c.pk, "texto": "Hola Ana"})
        m = MensajePreparado.objects.get(tipo=Categoria.GENERAL)
        assert r["Location"] == reverse("mensajeria:enviar", args=[m.pk])

    def test_lanzar_campana_desde_la_vista(self, cliente_verificado, estudio):
        cliente(consentimiento=True)
        r = cliente_verificado.post(
            reverse("mensajeria:campana_nueva"),
            {
                "nombre": "Flash otoño",
                "segmento": "marketing",
                "plantilla": Plantilla.para(Categoria.CAMPANA).pk,
                "fecha_inicio": hoy().isoformat(),
                "por_dia": 10,
            },
        )
        assert r.status_code == 302
        assert Campana.objects.get().mensajes.count() == 1
