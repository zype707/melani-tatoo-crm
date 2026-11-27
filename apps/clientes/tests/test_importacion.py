"""Importación de clientes por lotes desde CSV."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.clientes import importacion
from apps.clientes.models import Cliente, Etiqueta, EventoConsentimiento
from apps.cuentas.models import Usuario
from apps.nucleo.models import RegistroAuditoria

pytestmark = pytest.mark.django_db

CSV_BASICO = (
    "nombre,apellidos,telefono,email,fecha_nacimiento,etiquetas,acepta_promociones,cliente_desde\n"
    'Ana,López,(407) 555-0123,ana@ejemplo.com,1994-03-21,"VIP, fine line",sí,2023-06-10\n'
    "Bruno,Díaz,+34 612 345 678,,,,no,\n"
)


def analizar(texto, **kw):
    return importacion.analizar(texto, **kw)


class TestLectura:
    def test_utf8_con_bom(self):
        assert importacion.leer("﻿nombre\nAna".encode()) == "nombre\nAna"

    def test_windows_1252_de_excel(self):
        assert "Peña" in importacion.leer("nombre;telefono\nPeña;4075550123".encode("cp1252"))

    def test_vacio(self):
        with pytest.raises(importacion.ArchivoInvalido):
            importacion.leer(b"  \n ")

    def test_excel_sin_convertir(self):
        with pytest.raises(importacion.ArchivoInvalido, match="Excel"):
            importacion.leer(b"PK\x03\x04resto-del-xlsx")

    def test_demasiado_grande(self):
        with pytest.raises(importacion.ArchivoInvalido):
            importacion.leer(b"a" * (importacion.LIMITE_BYTES + 1))


class TestAnalisis:
    def test_basico(self):
        a = analizar(CSV_BASICO)
        assert [f.estado for f in a.filas] == ["nueva", "nueva"]
        ana = a.filas[0].datos
        assert ana["telefono"] == "+14075550123"
        assert ana["etiquetas"] == ["VIP", "fine line"]
        assert ana["acepta_promociones"] is True
        assert str(ana["fecha_nacimiento"]) == "1994-03-21"
        assert a.filas[1].datos["telefono"] == "+34612345678"
        assert a.con_promociones == 1

    def test_punto_y_coma_y_cabeceras_en_ingles(self):
        a = analizar("First Name;Last Name;Phone;E-mail\nAna;López;4075550123;ANA@x.com\n")
        assert a.delimitador == ";"
        assert a.mapa == {"First Name": "nombre", "Last Name": "apellidos", "Phone": "telefono", "E-mail": "email"}
        assert a.filas[0].estado == "nueva"

    def test_cabeceras_con_tildes_y_mayusculas(self):
        a = analizar("Nombre,Teléfono Móvil,Cumpleaños\nAna,4075550123,03/21/1994\n")
        assert a.mapa["Teléfono Móvil"] == "telefono"
        assert str(a.filas[0].datos["fecha_nacimiento"]) == "1994-03-21"

    def test_nombre_completo(self):
        a = analizar('cliente,telefono\nAna López García,4075550123\n"Díaz, Bruno",4075550124\n')
        assert (a.filas[0].datos["nombre"], a.filas[0].datos["apellidos"]) == ("Ana", "López García")
        assert (a.filas[1].datos["nombre"], a.filas[1].datos["apellidos"]) == ("Bruno", "Díaz")

    def test_sin_columna_nombre(self):
        with pytest.raises(importacion.ArchivoInvalido, match="nombre"):
            analizar("telefono,email\n4075550123,a@b.com\n")

    def test_solo_cabecera(self):
        with pytest.raises(importacion.ArchivoInvalido):
            analizar("nombre,telefono\n")

    @pytest.mark.parametrize(
        ("formato", "texto", "esperado"),
        [
            ("mdy", "03/04/1990", "1990-03-04"),
            ("dmy", "03/04/1990", "1990-04-03"),
            ("mdy", "25/12/1990", "1990-12-25"),  # el 25 no puede ser mes: se corrige solo
            ("dmy", "1990-12-25", "1990-12-25"),
            ("dmy", "25.12.90", "1990-12-25"),
        ],
    )
    def test_fechas(self, formato, texto, esperado):
        a = analizar(f"nombre,telefono,fecha_nacimiento\nAna,4075550123,{texto}\n", formato_fecha=formato)
        assert str(a.filas[0].datos["fecha_nacimiento"]) == esperado

    def test_errores_por_fila(self):
        a = analizar(
            "nombre,telefono,email,fecha_nacimiento\n"
            ",4075550123,,\n"  # sin nombre
            "Bea,12,,\n"  # teléfono imposible
            "Carla,,no-es-email,\n"  # email inválido
            "Dani,,,\n"  # sin contacto
            "Eva,4075550199,,31/31/1990\n"  # fecha imposible
            "Fran,4075550188,,\n"  # correcta
        )
        assert [f.estado for f in a.filas] == ["error"] * 5 + ["nueva"]
        assert "nombre" in a.filas[0].errores[0]
        assert a.filas[3].errores == ["Falta un dato de contacto: teléfono, email o Instagram."]
        assert a.filas[1].numero == 3  # número de línea del archivo (la cabecera es la 1)

    def test_duplicado_dentro_del_archivo(self):
        a = analizar("nombre,telefono\nAna,4075550123\nAna B,(407) 555-0123\n")
        assert [f.estado for f in a.filas] == ["nueva", "error"]
        assert "fila 2" in a.filas[1].errores[0]

    def test_ya_existe_por_telefono_o_email(self):
        Cliente.objects.create(nombre="Ana", telefono="+14075550123")
        Cliente.objects.create(nombre="Bea", email="bea@x.com")
        a = analizar("nombre,telefono,email\nAna,407-555-0123,\nBeatriz,,BEA@x.com\nCarla,4075550100,\n")
        assert [f.estado for f in a.filas] == ["existe", "existe", "nueva"]
        assert a.filas[1].existente_nombre == "Bea"

    def test_avisos_no_bloquean(self):
        a = analizar("nombre,telefono,canal,origen,promociones\nAna,4075550123,paloma,tiktok,quizá\n")
        f = a.filas[0]
        assert f.estado == "nueva"
        assert f.datos["canal_preferido"] == "whatsapp"
        assert f.datos["origen"] == "otro"
        assert f.datos["acepta_promociones"] is False
        assert len(f.avisos) == 3

    def test_origen_y_canal_reconocidos(self):
        a = analizar("nombre,ig,canal,origen\nAna,https://instagram.com/ana.tattoo/,SMS,Recomendación\n")
        d = a.filas[0].datos
        assert (d["instagram"], d["canal_preferido"], d["origen"]) == ("ana.tattoo", "sms", "recomendacion")

    def test_telefono_convertido_en_decimal_por_excel(self):
        a = analizar("nombre,telefono\nAna,4075550123.0\n")
        assert a.filas[0].datos["telefono"] == "+14075550123"

    def test_limite_de_filas(self, monkeypatch):
        monkeypatch.setattr(importacion, "LIMITE_FILAS", 2)
        with pytest.raises(importacion.ArchivoInvalido):
            analizar("nombre,email\nA,a@x.com\nB,b@x.com\nC,c@x.com\n")


class TestImportar:
    def test_crea_fichas_etiquetas_y_antiguedad(self, usuaria):
        r = importacion.importar(analizar(CSV_BASICO), etiqueta_lote="importadas", usuario=usuaria)
        assert r == {"creados": 2, "completados": 0, "omitidos": 0, "errores": 0, "consentimientos": 0}
        ana = Cliente.objects.get(nombre="Ana")
        assert sorted(e.nombre for e in ana.etiquetas.all()) == ["VIP", "fine line", "importadas"]
        assert ana.creado_en.date().isoformat() == "2023-06-10"
        assert Etiqueta.objects.get(nombre="importadas").clientes.count() == 2

    def test_sin_origen_no_registra_consentimiento(self):
        importacion.importar(analizar(CSV_BASICO))
        assert not Cliente.objects.get(nombre="Ana").marketing_consentimiento
        assert not EventoConsentimiento.objects.exists()

    def test_con_origen_registra_consentimiento(self, usuaria):
        r = importacion.importar(analizar(CSV_BASICO), origen_consentimiento="presencial", usuario=usuaria)
        ana = Cliente.objects.get(nombre="Ana")
        assert ana.marketing_consentimiento and ana.marketing_origen == "presencial"
        evento = EventoConsentimiento.objects.get()
        assert (evento.cliente, evento.tipo, evento.usuario) == (ana, "alta", usuaria)
        assert not Cliente.objects.get(nombre="Bruno").marketing_consentimiento
        assert r["consentimientos"] == 1

    def test_origen_peticion_baja_no_vale_como_alta(self):
        importacion.importar(analizar(CSV_BASICO), origen_consentimiento="peticion_baja")
        assert not Cliente.objects.filter(marketing_consentimiento=True).exists()

    def test_reutiliza_etiquetas_sin_distinguir_mayusculas(self):
        Etiqueta.objects.create(nombre="vip")
        importacion.importar(analizar(CSV_BASICO))
        assert Etiqueta.objects.filter(nombre__iexact="vip").count() == 1

    def test_existentes_se_omiten_por_defecto(self):
        ana = Cliente.objects.create(nombre="Ana", telefono="+14075550123")
        r = importacion.importar(analizar(CSV_BASICO))
        assert r["creados"] == 1 and r["omitidos"] == 1
        ana.refresh_from_db()
        assert ana.email == ""

    def test_completar_solo_rellena_lo_vacio(self, usuaria):
        ana = Cliente.objects.create(nombre="Ana", apellidos="Original", telefono="+14075550123")
        r = importacion.importar(
            analizar(CSV_BASICO), si_existe="completar", origen_consentimiento="verbal", usuario=usuaria
        )
        ana.refresh_from_db()
        assert ana.apellidos == "Original"  # no se sobrescribe
        assert ana.email == "ana@ejemplo.com"  # se completa
        assert ana.marketing_consentimiento
        assert r["completados"] == 1 and r["creados"] == 1


class TestVistas:
    def subir(self, client, contenido, **extra):
        archivo = SimpleUploadedFile("clientes.csv", contenido.encode("utf-8"), content_type="text/csv")
        datos = {"archivo": archivo, "formato_fecha": "mdy", "si_existe": "omitir", "etiqueta_lote": "", **extra}
        return client.post(reverse("clientes:importar"), datos)

    def test_flujo_completo(self, cliente_verificado):
        assert cliente_verificado.get(reverse("clientes:importar")).status_code == 200
        r = self.subir(cliente_verificado, CSV_BASICO + "Mal,,,\n", etiqueta_lote="lote 1")
        assert r.status_code == 302 and r["Location"] == reverse("clientes:importar_revisar")
        assert not Cliente.objects.exists()  # la revisión no guarda nada

        html = cliente_verificado.get(reverse("clientes:importar_revisar")).content.decode()
        assert "Ana López" in html and "Falta un dato de contacto" in html
        assert "Importar 2 clientes" in html

        errores = cliente_verificado.get(reverse("clientes:importar_errores"))
        assert errores["Content-Type"].startswith("text/csv")
        assert "Mal" in errores.content.decode("utf-8-sig")

        r = cliente_verificado.post(
            reverse("clientes:importar_revisar"), {"confirmar": "1", "origen_consentimiento": "presencial"}
        )
        assert r.status_code == 302 and r["Location"] == reverse("clientes:importar_listo")
        assert Cliente.objects.count() == 2
        assert Cliente.objects.get(nombre="Ana").marketing_consentimiento
        assert RegistroAuditoria.objects.filter(accion="importacion").exists()

        html = cliente_verificado.get(reverse("clientes:importar_listo")).content.decode()
        assert "Importación terminada" in html and "lote 1" in html
        assert cliente_verificado.get(reverse("clientes:importar_errores")).status_code == 200

        # La importación pendiente ya no existe: volver a revisar redirige a subir otro archivo
        assert cliente_verificado.get(reverse("clientes:importar_revisar")).status_code == 302

    def test_cancelar_no_guarda_nada(self, cliente_verificado):
        self.subir(cliente_verificado, CSV_BASICO)
        r = cliente_verificado.post(reverse("clientes:importar_revisar"), {"cancelar": "1"})
        assert r.status_code == 302
        assert not Cliente.objects.exists()

    def test_archivo_sin_nombre_muestra_error(self, cliente_verificado):
        r = self.subir(cliente_verificado, "telefono\n4075550123\n")
        assert r.status_code == 200
        assert "No encuentro la columna del nombre" in r.content.decode()

    def test_plantilla_se_puede_reimportar(self, cliente_verificado):
        r = cliente_verificado.get(reverse("clientes:importar_plantilla"))
        assert r["Content-Disposition"].startswith("attachment")
        texto = importacion.leer(r.content)
        a = importacion.analizar(texto)
        assert [f.estado for f in a.filas] == ["nueva", "nueva"]
        assert not a.ignoradas

    def test_plantilla_en_ingles(self, cliente_verificado):
        r = cliente_verificado.get(reverse("clientes:importar_plantilla"), HTTP_ACCEPT_LANGUAGE="en")
        assert importacion.leer(r.content).startswith("first_name,last_name,phone")

    def test_solo_propietaria(self, client):
        ayudante = Usuario.objects.create_user(
            usuario="ayu", password="Una-clave-larga-de-pruebas-2026", nombre="Ayu", rol="ayudante"
        )
        client.force_login(ayudante)
        assert client.get(reverse("clientes:importar")).status_code == 403
        assert client.get(reverse("clientes:importar_plantilla")).status_code == 403
        assert "Importar CSV" not in client.get(reverse("clientes:lista")).content.decode()

    def test_boton_en_la_lista(self, cliente_verificado):
        html = cliente_verificado.get(reverse("clientes:lista")).content.decode()
        assert reverse("clientes:importar") in html
