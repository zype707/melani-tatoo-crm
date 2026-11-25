import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cuentas.models import Usuario
from apps.finanzas import servicios
from apps.finanzas.models import Gasto, Pago
from apps.nucleo import graficos
from apps.nucleo.models import RegistroAuditoria

pytestmark = pytest.mark.django_db


@pytest.fixture
def movimientos(db):
    hoy = timezone.localdate()
    c = Cliente.objects.create(nombre='=HYPERLINK("http://malo")', telefono="+14075550100")
    Pago.objects.create(cliente=c, importe=Decimal("450"), tipo="sesion", fecha=hoy)
    Pago.objects.create(cliente=c, importe=Decimal("100"), tipo="sena", fecha=hoy)
    Pago.objects.create(cliente=c, importe=Decimal("100"), tipo="sena", fecha=hoy, devuelto=True)
    Gasto.objects.create(concepto="+cmd|' /C calc'!A0", categoria="material", importe=Decimal("80"), fecha=hoy)
    return hoy


class TestFinanzas:
    def test_resumen_mes(self, movimientos):
        datos = servicios.resumen_mes(movimientos.year, movimientos.month)
        assert datos["ingresos"] == Decimal("550")  # el devuelto no cuenta
        assert datos["gastos"] == Decimal("80")
        assert datos["balance"] == Decimal("470")

    def test_csv_sin_inyeccion_de_formulas(self, movimientos):
        salida = io.StringIO()
        servicios.escribir_csv(salida, movimientos, movimientos)
        filas = list(csv.reader(io.StringIO(salida.getvalue().lstrip("﻿"))))
        celdas = [c for f in filas[1:] for c in f[2:4]]
        assert all(not c.startswith(("=", "+", "-", "@")) for c in celdas)
        assert any(c.startswith("'=HYPERLINK") for c in celdas)

    def test_vista_y_exportacion_auditada(self, cliente_verificado, movimientos):
        assert cliente_verificado.get(reverse("finanzas:resumen")).status_code == 200
        r = cliente_verificado.post(
            reverse("finanzas:exportar"), {"desde": movimientos.isoformat(), "hasta": movimientos.isoformat()}
        )
        assert r["Content-Type"].startswith("text/csv")
        assert RegistroAuditoria.objects.filter(accion="exportacion").exists()

    def test_ayudante_no_ve_finanzas(self, client, db):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        ayudante = Usuario.objects.create_user("ayu@ejemplo.com", "Clave-ayudante-2026", nombre="Ayu", rol="ayudante")
        d = TOTPDevice.objects.create(user=ayudante, confirmed=True)
        client.force_login(ayudante)
        s = client.session
        s["otp_device_id"] = d.persistent_id
        s.save()
        assert client.get(reverse("finanzas:resumen")).status_code == 403
        assert "Finanzas" not in client.get("/").content.decode()

    def test_gasto_nuevo(self, cliente_verificado):
        cliente_verificado.post(
            reverse("finanzas:gasto_nuevo"),
            {
                "fecha": timezone.localdate().isoformat(),
                "categoria": "alquiler",
                "concepto": "Local",
                "importe": "650",
                "metodo": "transferencia",
            },
        )
        assert Gasto.objects.get().importe == 650

    def test_serie_mensual(self, movimientos):
        serie = servicios.serie_mensual(movimientos, 3)
        assert len(serie) == 3
        assert serie[-1]["ingresos"] == Decimal("550")


class TestGraficos:
    def test_geometria(self):
        g = graficos.barras(["a", "b"], [{"nombre": "I", "valores": [100, 50], "clase": "serie-a"}], alto=200)
        b1, b2 = g["grupos"][0]["barras"][0], g["grupos"][1]["barras"][0]
        assert b1["alto"] == pytest.approx(2 * b2["alto"], rel=0.01)
        assert b1["y"] + b1["alto"] == pytest.approx(g["base_y"])
        assert g["lineas"][0]["valor"] == 0

    def test_sin_datos(self):
        g = graficos.barras(["a"], [{"nombre": "I", "valores": [0]}])
        assert g["grupos"][0]["barras"][0]["alto"] == 0


class TestPanel:
    def test_panel_con_metricas(self, cliente_verificado, movimientos):
        from apps.agenda.models import Cita, TipoCita

        t = TipoCita.objects.create(nombre="Sesión", duracion_minutos=60)
        c = Cliente.objects.create(nombre="Eva", telefono="+14075550111")
        ahora = timezone.now()
        Cita.objects.create(
            cliente=c,
            tipo=t,
            inicio=ahora - timedelta(days=10),
            fin=ahora - timedelta(days=10, hours=-1),
            estado="realizada",
        )
        Cita.objects.create(
            cliente=c,
            tipo=t,
            inicio=ahora - timedelta(days=5),
            fin=ahora - timedelta(days=5, hours=-1),
            estado="no_show",
        )
        r = cliente_verificado.get("/")
        assert r.status_code == 200
        assert r.context["no_show"]["tasa"] == 0.5
        assert "<svg" in r.content.decode()
