"""Ayuda integrada: tutorial, ayuda de cada pantalla, pistas y primeros pasos."""

import re

import pytest
from django.urls import get_resolver, reverse
from django.utils import translation

from apps.clientes.models import Cliente
from apps.cuentas.models import Usuario
from apps.nucleo import ayuda

pytestmark = pytest.mark.django_db
EN = {"HTTP_ACCEPT_LANGUAGE": "en-US,en;q=0.9"}


def nombres_de_url() -> set[str]:
    nombres = set()

    def recorrer(patrones, ns=""):
        for p in patrones:
            if hasattr(p, "url_patterns"):
                recorrer(p.url_patterns, f"{ns}{p.namespace}:" if p.namespace else ns)
            elif p.name:
                nombres.add(f"{ns}{p.name}")

    recorrer(get_resolver().url_patterns)
    return nombres


class TestRegistro:
    def test_las_vistas_documentadas_existen(self):
        existentes = nombres_de_url()
        for p in ayuda.PANTALLAS:
            for vista in p.vistas:
                assert vista in existentes, f"{p.clave}: la vista {vista} no existe"

    def test_cada_vista_tiene_una_sola_pantalla(self):
        vistas = [v for p in ayuda.PANTALLAS for v in p.vistas]
        assert len(vistas) == len(set(vistas))

    @pytest.mark.parametrize(
        "vista",
        [
            "panel:inicio",
            "agenda:calendario",
            "agenda:detalle",
            "agenda:nueva",
            "mensajeria:bandeja",
            "mensajeria:campanas",
            "mensajeria:plantillas",
            "clientes:lista",
            "clientes:ficha",
            "clientes:importar",
            "solicitudes:lista",
            "solicitudes:detalle",
            "catalogo:lista",
            "finanzas:resumen",
            "ia:asistente",
            "nucleo:ajustes",
            "cuentas:cuenta",
            "ayuda:inicio",
        ],
    )
    def test_las_pantallas_principales_tienen_ayuda(self, vista):
        p = ayuda.pantalla_para(vista)
        assert p is not None and p.botones and p.resumen

    def test_los_botones_citados_existen(self):
        for p in ayuda.PANTALLAS:
            for b in p.botones:
                assert b.clave in ayuda.BOTONES, f"{p.clave}: botón desconocido {b.clave}"
        textos = [t for c in ayuda.CAPITULOS for t in (c.intro, *c.pasos, c.consejo)]
        for texto in textos:
            for clave in re.findall(r"\[\[([a-z_]+)\]\]", str(texto)):
                assert clave in ayuda.BOTONES, f"[[{clave}]] no está en BOTONES"

    def test_los_capitulos_citan_pantallas_reales(self):
        claves = {p.clave for p in ayuda.PANTALLAS}
        capitulos = {c.clave for c in ayuda.CAPITULOS}
        for c in ayuda.CAPITULOS:
            assert set(c.pantallas) <= claves
        for p in ayuda.PANTALLAS:
            assert p.capitulo in capitulos, f"{p.clave}: capítulo {p.capitulo} inexistente"

    def test_marcado_escapa_y_dibuja_botones(self):
        html = ayuda.marcado("<b>hola</b> pulsa [[nueva_cita]] **ya** [[no_existe]]")
        assert "&lt;b&gt;hola&lt;/b&gt;" in html
        assert 'class="muestra muestra-primario"' in html and "Nueva cita" in html
        assert "<strong>ya</strong>" in html
        assert "[[no_existe]]" in html

    def test_todo_el_contenido_esta_traducido_al_ingles(self):
        iguales_permitidos = {"WhatsApp", "VIP", "CSV", "Flash", "No-show", "Variable", "{nombre}"}
        textos = []
        for p in ayuda.PANTALLAS:
            textos += [p.titulo, p.resumen, *p.consejos, *(b.texto for b in p.botones)]
        for c in ayuda.CAPITULOS:
            textos += [c.titulo, c.resumen, c.intro, *c.pasos, *([c.consejo] if c.consejo else [])]
        for pregunta, respuesta in ayuda.PREGUNTAS:
            textos += [pregunta, respuesta]
        for termino, definicion in ayuda.GLOSARIO:
            textos += [termino, definicion]
        textos += [etiqueta for _i, etiqueta, _e in ayuda.BOTONES.values()]
        sin_traducir = []
        for t in textos:
            with translation.override("es"):
                es = str(t)
            with translation.override("en"):
                en = str(t)
            if es == en and es not in iguales_permitidos and re.search(r"[a-záéíóúñ]{4,}", es):
                sin_traducir.append(es)
        assert not sin_traducir, sin_traducir[:5]


class TestTutorial:
    def test_se_ve_en_espanol(self, cliente_verificado):
        html = cliente_verificado.get(reverse("ayuda:inicio")).content.decode()
        assert "Cómo usar" in html and "Primeros pasos" in html
        for c in ayuda.CAPITULOS:
            assert f'id="{c.clave}"' in html
        assert 'id="pantalla-importar"' in html
        assert "data-filtrar-ayuda" in html

    def test_se_ve_en_ingles(self, cliente_verificado):
        html = cliente_verificado.get(reverse("ayuda:inicio"), **EN).content.decode()
        assert "How to use" in html and "First steps" in html
        assert "Primeros pasos" not in html

    def test_ayudante_no_ve_lo_reservado(self, client):
        ayudante = Usuario.objects.create_user(usuario="ayu", password="x" * 14, nombre="Ayu", rol="ayudante")
        client.force_login(ayudante)
        html = client.get(reverse("ayuda:inicio")).content.decode()
        assert 'id="pantalla-finanzas"' not in html and 'id="pantalla-importar"' not in html
        assert "Importar CSV" not in html

    def test_enlace_en_el_menu(self, cliente_verificado):
        html = cliente_verificado.get(reverse("panel:inicio")).content.decode()
        assert reverse("ayuda:inicio") in html


class TestAyudaDePantalla:
    def test_el_panel_de_ayuda_es_el_de_la_pantalla(self, cliente_verificado):
        html = cliente_verificado.get(reverse("agenda:calendario")).content.decode()
        assert 'id="dialogo-ayuda"' in html
        assert "Qué hace cada botón" in html and "Lista de espera" in html

    def test_botones_con_explicacion(self, cliente_verificado):
        html = cliente_verificado.get(reverse("clientes:lista")).content.decode()
        assert html.count("data-ayuda=") >= 3

    def test_pista_se_cierra_y_no_vuelve(self, cliente_verificado, usuaria, htmx):
        url = reverse("clientes:lista")
        assert 'class="pista"' in cliente_verificado.get(url).content.decode()
        r = cliente_verificado.post(reverse("ayuda:pista"), {"clave": "clientes"}, **htmx)
        assert r.status_code == 200 and r.content == b""
        assert 'class="pista"' not in cliente_verificado.get(url).content.decode()
        usuaria.refresh_from_db()
        assert usuaria.ayudas_cerradas == ["clientes"]

    def test_pista_sin_javascript_vuelve_a_la_pagina(self, cliente_verificado):
        r = cliente_verificado.post(reverse("ayuda:pista"), {"clave": "agenda", "next": "/agenda/"})
        assert r.status_code == 302 and r["Location"] == "/agenda/"

    def test_no_redirige_fuera(self, cliente_verificado):
        r = cliente_verificado.post(reverse("ayuda:pista"), {"clave": "agenda", "next": "https://malo.example/"})
        assert r["Location"] == reverse("ayuda:inicio")

    def test_clave_desconocida_se_ignora(self, cliente_verificado, usuaria):
        cliente_verificado.post(reverse("ayuda:pista"), {"clave": "inventada"})
        usuaria.refresh_from_db()
        assert usuaria.ayudas_cerradas == []

    def test_ocultar_y_volver_a_mostrar_todas(self, cliente_verificado, usuaria):
        url = reverse("clientes:lista")
        cliente_verificado.post(reverse("ayuda:pista"), {"clave": "agenda"})
        cliente_verificado.post(reverse("ayuda:paso"), {"paso": "horario", "hecho": "1"})
        cliente_verificado.post(reverse("ayuda:preferencias"), {"mostrar": "0"})
        assert 'class="pista"' not in cliente_verificado.get(url).content.decode()
        cliente_verificado.post(reverse("ayuda:preferencias"), {"mostrar": "1"})
        usuaria.refresh_from_db()
        assert usuaria.ayudas_visibles
        assert usuaria.ayudas_cerradas == ["paso:horario"]  # las pistas vuelven; los pasos marcados se quedan
        assert 'class="pista"' in cliente_verificado.get(url).content.decode()

    def test_solo_por_post(self, cliente_verificado):
        assert cliente_verificado.get(reverse("ayuda:pista")).status_code == 405
        assert cliente_verificado.get(reverse("ayuda:preferencias")).status_code == 405

    def test_requiere_sesion(self, client):
        assert client.get(reverse("ayuda:inicio")).status_code == 302

    def test_preferencia_en_mi_cuenta(self, cliente_verificado):
        html = cliente_verificado.get(reverse("cuentas:cuenta")).content.decode()
        assert reverse("ayuda:preferencias") in html


class TestPrimerosPasos:
    def test_se_detecta_lo_que_se_puede(self, usuaria):
        pasos = {p.clave: p for p in ayuda.primeros_pasos(usuaria)}
        assert not pasos["clientes"].hecho
        Cliente.objects.create(nombre="Ana", telefono="+14075550123")
        pasos = {p.clave: p for p in ayuda.primeros_pasos(usuaria)}
        assert pasos["clientes"].hecho and not pasos["clientes"].manual

    def test_marcar_a_mano(self, cliente_verificado, usuaria):
        cliente_verificado.post(reverse("ayuda:paso"), {"paso": "plantillas", "hecho": "1"})
        usuaria.refresh_from_db()
        assert {p.clave: p for p in ayuda.primeros_pasos(usuaria)}["plantillas"].hecho
        cliente_verificado.post(reverse("ayuda:paso"), {"paso": "plantillas", "hecho": "0"})
        usuaria.refresh_from_db()
        assert not {p.clave: p for p in ayuda.primeros_pasos(usuaria)}["plantillas"].hecho

    def test_paso_inventado_se_ignora(self, cliente_verificado, usuaria):
        cliente_verificado.post(reverse("ayuda:paso"), {"paso": "hackear", "hecho": "1"})
        usuaria.refresh_from_db()
        assert usuaria.ayudas_cerradas == []

    def test_ayudante_sin_pasos_de_propietaria(self):
        ayudante = Usuario.objects.create_user(usuario="ayu", password="x" * 14, nombre="Ayu", rol="ayudante")
        claves = {p.clave for p in ayuda.primeros_pasos(ayudante)}
        assert "marca" not in claves and "consentimiento" not in claves and "clientes" in claves

    def test_tarjeta_en_hoy_y_ocultar(self, cliente_verificado, htmx):
        assert 'id="primeros-pasos"' in cliente_verificado.get("/").content.decode()
        cliente_verificado.post(reverse("ayuda:pista"), {"clave": "primeros_pasos"}, **htmx)
        assert 'id="primeros-pasos"' not in cliente_verificado.get("/").content.decode()
        # En el tutorial siguen estando
        assert 'id="primeros-pasos"' in cliente_verificado.get(reverse("ayuda:inicio")).content.decode()
