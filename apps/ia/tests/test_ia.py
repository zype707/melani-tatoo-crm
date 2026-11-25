import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Cita, SolicitudReserva, TipoCita
from apps.clientes.models import Cliente, DatosSalud, Tatuaje
from apps.ia import busqueda, proveedor, servicios
from apps.ia.models import UsoIA
from apps.ia.privacidad import perfil_cliente, redactar_pii
from apps.ia.proveedor import ErrorIA, Resultado
from apps.nucleo.models import AjustesEstudio

pytestmark = pytest.mark.django_db


class Falso:
    """Proveedor de pruebas: registra lo que recibiría OpenAI."""

    def __init__(self, respuesta_json=None, error=None):
        self.llamadas = []
        self.respuesta_json = respuesta_json or {}
        self.error = error

    def texto(self, instrucciones, entrada, max_tokens=600):
        self.llamadas.append(instrucciones + "\n" + entrada)
        if self.error:
            raise self.error
        return Resultado("Hola desde la IA", 10, 5)

    def json(self, instrucciones, entrada, nombre, esquema, max_tokens=900):
        self.llamadas.append(instrucciones + "\n" + entrada)
        if self.error:
            raise self.error
        return self.respuesta_json, Resultado("{}", 10, 5)


@pytest.fixture
def falso():
    f = Falso()
    proveedor._proveedor_pruebas = f
    yield f
    proveedor._proveedor_pruebas = None


@pytest.fixture
def cliente(db):
    c = Cliente.objects.create(
        nombre="Lucía",
        apellidos="Méndez-Secreto",
        telefono="+14075550123",
        email="lucia@privado.com",
        instagram="lu.secreta",
        fecha_nacimiento="1994-03-12",
        notas="NOTA PRIVADA",
    )
    DatosSalud.objects.create(cliente=c, alergias="ALERGIA-LATEX", medicacion="MEDICAMENTO-X", diabetes=True)
    Tatuaje.objects.create(cliente=c, titulo="Rosa", zona="antebrazo", estilo="fine_line")
    return c


class TestPrivacidad:
    def test_perfil_sin_datos_sensibles(self, cliente):
        texto = json.dumps(perfil_cliente(cliente), ensure_ascii=False)
        for prohibido in (
            "Méndez",
            "4075550123",
            "lucia@privado",
            "lu.secreta",
            "1994",
            "NOTA PRIVADA",
            "ALERGIA",
            "MEDICAMENTO",
            "diabetes",
        ):
            assert prohibido not in texto
        assert "Lucía" in texto and "Antebrazo" in texto

    def test_redactar_pii(self):
        limpio = redactar_pii(
            "Escríbeme a ana@x.com o al (407) 555-0199, mira https://x.co @ana_tattoo 4111 1111 1111 1111"
        )
        assert "ana@x.com" not in limpio and "555-0199" not in limpio and "https" not in limpio
        assert "@ana_tattoo" not in limpio and "4111" not in limpio

    def test_lo_que_sale_hacia_la_ia(self, cliente, falso):
        servicios.redactar_mensaje(cliente, "felicitar", "llámala al 407 555 0123")
        enviado = falso.llamadas[0]
        assert "ALERGIA" not in enviado and "MEDICAMENTO" not in enviado
        assert "4075550123" not in enviado.replace(" ", "") and "Méndez" not in enviado
        assert UsoIA.objects.get().exito

    def test_resumen_de_cita_sin_salud(self, cliente, falso):
        t = TipoCita.objects.create(nombre="Sesión", duracion_minutos=120)
        ahora = timezone.now() + timedelta(days=1)
        cita = Cita.objects.create(
            cliente=cliente, tipo=t, inicio=ahora, fin=ahora + timedelta(hours=2), notas_sesion="PIEL REACTIVA"
        )
        servicios.resumen_cita(cita)
        assert "ALERGIA" not in falso.llamadas[0] and "PIEL REACTIVA" not in falso.llamadas[0]


class TestControl:
    def test_sin_clave_no_disponible(self, db, settings):
        settings.OPENAI_API_KEY = ""
        assert not servicios.disponible()
        with pytest.raises(ErrorIA):
            servicios.redactar_mensaje(Cliente(nombre="X"), "x")

    def test_desactivada_en_ajustes(self, falso):
        a = AjustesEstudio.obtener()
        a.ia_activa = False
        a.save()
        assert not servicios.disponible()

    def test_cuota_mensual(self, cliente, falso):
        a = AjustesEstudio.obtener()
        a.ia_limite_mensual = 2
        a.save()
        servicios.redactar_mensaje(cliente, "a")
        servicios.redactar_mensaje(cliente, "b")
        with pytest.raises(ErrorIA) as exc:
            servicios.redactar_mensaje(cliente, "c")
        assert exc.value.codigo == "cuota"
        assert len(falso.llamadas) == 2

    def test_error_registrado(self, cliente):
        proveedor._proveedor_pruebas = Falso(error=ErrorIA("tarda", "timeout"))
        try:
            with pytest.raises(ErrorIA):
                servicios.redactar_mensaje(cliente, "a")
            assert UsoIA.objects.get().error == "timeout"
        finally:
            proveedor._proveedor_pruebas = None

    def test_la_app_funciona_sin_ia(self, cliente_verificado, settings, cliente):
        settings.OPENAI_API_KEY = ""
        for url in (
            "/",
            reverse("clientes:ficha", args=[cliente.pk]),
            reverse("mensajeria:nuevo"),
            reverse("ia:asistente"),
        ):
            r = cliente_verificado.get(url)
            assert r.status_code == 200
        assert "Redactar con IA" not in cliente_verificado.get(reverse("mensajeria:nuevo")).content.decode()
        r = cliente_verificado.get(reverse("ia:asistente"), {"q": "fine line antebrazo"})
        assert "Lucía" in r.content.decode()


class TestBusqueda:
    def test_validar_descarta_valores_raros(self):
        f = busqueda.validar(
            {
                "estilos": ["fine_line", "DROP TABLE"],
                "zonas": ["antebrazo", "'; --"],
                "sin_visita_meses": "9999",
                "orden": "pk; delete",
                "cumple_mes": 13,
            }
        )
        assert f["estilos"] == ["fine_line"] and f["zonas"] == ["antebrazo"]
        assert f["sin_visita_meses"] is None and f["orden"] == "nombre" and f["cumple_mes"] is None

    def test_aplicar(self, cliente):
        otro = Cliente.objects.create(nombre="Otro", telefono="+14075550999")
        Tatuaje.objects.create(cliente=otro, titulo="Dragón", zona="espalda", estilo="japones")
        qs, _ = busqueda.aplicar({"estilos": ["fine_line"], "zonas": ["antebrazo"]})
        assert list(qs) == [cliente]

    def test_interprete_local(self):
        f = busqueda.interpretar_local("VIP con fine line en el antebrazo que no vienen desde hace 6 meses")
        assert f["estilos"] == ["fine_line"] and f["zonas"] == ["antebrazo"]
        assert f["etiquetas"] == ["VIP"] and f["sin_visita_meses"] == 6

    def test_busqueda_con_ia(self, cliente_verificado, cliente, falso):
        falso.respuesta_json = {
            "estilos": ["fine_line"],
            "zonas": [],
            "tamanos": [],
            "etiquetas": [],
            "estado_tatuaje": None,
            "sin_visita_meses": None,
            "visita_ultimos_meses": None,
            "cumple_mes": None,
            "gasto_minimo": None,
            "solo_promociones": None,
            "texto": None,
            "orden": "nombre",
        }
        r = cliente_verificado.get(reverse("ia:buscar"), {"q": "las de línea fina"})
        assert "Interpretado por IA" in r.content.decode() and "Lucía" in r.content.decode()


class TestVistasIA:
    def test_triaje(self, cliente_verificado, falso, htmx):
        falso.respuesta_json = {
            "resumen": "Rosa fina",
            "estilo": "fine_line",
            "zona": "antebrazo",
            "tamano": "pequeno",
            "sesiones_estimadas": 1,
            "horas_estimadas": 2,
            "complejidad": "baja",
            "preguntas": ["¿Color o negro?"],
        }
        s = SolicitudReserva.objects.create(
            nombre="Ana",
            telefono="+14075550101",
            fecha_nacimiento="1990-01-01",
            descripcion="Una rosa, mi email es ana@x.com",
        )
        r = cliente_verificado.post(reverse("ia:triaje", args=[s.pk]), **htmx)
        assert "¿Color o negro?" in r.content.decode()
        s.refresh_from_db()
        assert s.triaje["complejidad"] == "baja"
        assert "ana@x.com" not in falso.llamadas[0]

    def test_redactar_y_respuesta(self, cliente_verificado, cliente, falso, htmx):
        r = cliente_verificado.post(
            reverse("ia:redactar"), {"cliente": cliente.pk, "objetivo": "x", "texto": ""}, **htmx
        )
        assert "Hola desde la IA" in r.content.decode()
        r = cliente_verificado.post(reverse("ia:respuesta"), {"recibido": "¿Precio?", "cliente": cliente.pk}, **htmx)
        assert "Hola desde la IA" in r.content.decode() and "wa.me" in r.content.decode()

    def test_error_amigable(self, cliente_verificado, cliente, htmx):
        proveedor._proveedor_pruebas = Falso(error=ErrorIA("El modelo «x» no está disponible.", "modelo"))
        try:
            r = cliente_verificado.post(reverse("ia:retencion", args=[cliente.pk]), **htmx)
            assert r.status_code == 200 and "no está disponible" in r.content.decode()
        finally:
            proveedor._proveedor_pruebas = None
