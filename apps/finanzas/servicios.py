import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils.dates import MONTHS_3
from django.utils.translation import gettext as _

from .models import Gasto, Pago


def limites_mes(anio: int, mes: int) -> tuple[date, date]:
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def mes_anterior(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def ingresos(desde: date, hasta: date) -> Decimal:
    return Pago.objects.filter(devuelto=False, fecha__range=(desde, hasta)).aggregate(t=Sum("importe"))["t"] or Decimal(
        0
    )


def gastos(desde: date, hasta: date) -> Decimal:
    return Gasto.objects.filter(fecha__range=(desde, hasta)).aggregate(t=Sum("importe"))["t"] or Decimal(0)


def resumen_mes(anio: int, mes: int) -> dict:
    desde, hasta = limites_mes(anio, mes)
    pagos = Pago.objects.filter(devuelto=False, fecha__range=(desde, hasta))
    por_tipo = {
        Pago.Tipo(f["tipo"]).label: f["t"] for f in pagos.values("tipo").annotate(t=Sum("importe")).order_by("-t")
    }
    gastos_mes = Gasto.objects.filter(fecha__range=(desde, hasta))
    por_categoria = {
        Gasto.Categoria(f["categoria"]).label: f["t"]
        for f in gastos_mes.values("categoria").annotate(t=Sum("importe")).order_by("-t")
    }
    total_i = sum(por_tipo.values(), Decimal(0))
    total_g = sum(por_categoria.values(), Decimal(0))
    return {
        "desde": desde,
        "hasta": hasta,
        "ingresos": total_i,
        "gastos": total_g,
        "balance": total_i - total_g,
        "por_tipo": por_tipo,
        "por_categoria": por_categoria,
    }


def serie_mensual(hasta: date, meses: int = 12) -> list[dict]:
    inicio = hasta.replace(day=1)
    for _x in range(meses - 1):
        inicio = mes_anterior(inicio)
    fin = limites_mes(hasta.year, hasta.month)[1]
    i = {
        r["m"].date() if hasattr(r["m"], "date") else r["m"]: r["t"]
        for r in Pago.objects.filter(devuelto=False, fecha__range=(inicio, fin))
        .annotate(m=TruncMonth("fecha"))
        .values("m")
        .annotate(t=Sum("importe"))
    }
    g = {
        r["m"].date() if hasattr(r["m"], "date") else r["m"]: r["t"]
        for r in Gasto.objects.filter(fecha__range=(inicio, fin))
        .annotate(m=TruncMonth("fecha"))
        .values("m")
        .annotate(t=Sum("importe"))
    }
    serie = []
    actual = inicio
    while actual <= hasta:
        serie.append(
            {
                "mes": actual,
                "etiqueta": MONTHS_3[actual.month],
                "ingresos": i.get(actual, Decimal(0)),
                "gastos": g.get(actual, Decimal(0)),
            }
        )
        actual = (actual + timedelta(days=32)).replace(day=1)
    return serie


def movimientos(desde: date, hasta: date) -> list[dict]:
    filas = []
    for p in Pago.objects.filter(fecha__range=(desde, hasta)).select_related("cliente"):
        filas.append(
            {
                "fecha": p.fecha,
                "tipo": _("Ingreso"),
                "concepto": p.get_tipo_display(),
                "persona": p.cliente.nombre_completo if p.cliente else "",
                "metodo": p.get_metodo_display(),
                "importe": Decimal(0) if p.devuelto else p.importe,
                "devuelto": p.devuelto,
                "obj": p,
                "es_pago": True,
            }
        )
    for g in Gasto.objects.filter(fecha__range=(desde, hasta)):
        filas.append(
            {
                "fecha": g.fecha,
                "tipo": _("Gasto"),
                "concepto": f"{g.get_categoria_display()} · {g.concepto}",
                "persona": "",
                "metodo": g.get_metodo_display(),
                "importe": -g.importe,
                "devuelto": False,
                "obj": g,
                "es_pago": False,
            }
        )
    filas.sort(key=lambda f: (f["fecha"], f["tipo"]), reverse=True)
    return filas


def _celda_segura(valor) -> str:
    """Evita la inyección de fórmulas al abrir el CSV en Excel o Sheets."""
    texto = "" if valor is None else str(valor)
    if texto and texto[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + texto
    return texto


def escribir_csv(salida, desde: date, hasta: date) -> int:
    salida.write("﻿")  # BOM: Excel abre bien las tildes
    w = csv.writer(salida)
    w.writerow([_("Fecha"), _("Tipo"), _("Concepto"), _("Cliente"), _("Método"), _("Importe"), _("Devuelto")])
    filas = movimientos(desde, hasta)
    for f in sorted(filas, key=lambda f: f["fecha"]):
        w.writerow(
            [
                f["fecha"].isoformat(),
                f["tipo"],
                _celda_segura(f["concepto"]),
                _celda_segura(f["persona"]),
                f["metodo"],
                f"{f['importe']:.2f}",
                _("sí") if f["devuelto"] else "",
            ]
        )
    return len(filas)
