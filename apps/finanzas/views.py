from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente
from apps.nucleo import graficos
from apps.nucleo.auditoria import Accion, registrar
from apps.nucleo.decoradores import solo_propietaria

from . import servicios
from .forms import ExportarForm, GastoForm, PagoSueltoForm
from .models import Gasto, Pago


def _mes(request) -> date:
    texto = request.GET.get("mes", "")
    try:
        anio, mes = (int(x) for x in texto.split("-"))
        return date(anio, mes, 1)
    except ValueError:
        return timezone.localdate().replace(day=1)


@solo_propietaria
def resumen(request):
    mes = _mes(request)
    datos = servicios.resumen_mes(mes.year, mes.month)
    anterior = servicios.mes_anterior(mes)
    datos_ant = servicios.resumen_mes(anterior.year, anterior.month)
    serie = servicios.serie_mensual(datos["hasta"], 12)
    grafico = graficos.barras(
        [s["etiqueta"] for s in serie],
        [
            {"nombre": "Ingresos", "valores": [s["ingresos"] for s in serie], "clase": "serie-a"},
            {"nombre": "Gastos", "valores": [s["gastos"] for s in serie], "clase": "serie-b"},
        ],
        resaltar=len(serie) - 1,
    )
    variacion = None
    if datos_ant["ingresos"]:
        variacion = float((datos["ingresos"] - datos_ant["ingresos"]) / datos_ant["ingresos"])
    siguiente = (mes.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
    return render(
        request,
        "finanzas/resumen.html",
        {
            "mes": mes,
            "datos": datos,
            "anterior": datos_ant,
            "variacion": variacion,
            "grafico": grafico,
            "movimientos": servicios.movimientos(datos["desde"], datos["hasta"]),
            "mes_anterior": anterior,
            "mes_siguiente": siguiente if siguiente <= timezone.localdate() else None,
            "exportar": ExportarForm(initial={"desde": datos["desde"], "hasta": datos["hasta"]}),
        },
    )


@solo_propietaria
def gasto_formulario(request, pk=None):
    gasto = get_object_or_404(Gasto, pk=pk) if pk else None
    form = GastoForm(request.POST or None, instance=gasto)
    if request.method == "POST":
        if gasto and "borrar" in request.POST:
            gasto.delete()
            messages.success(request, "Gasto eliminado.")
            return redirect("finanzas:resumen")
        if form.is_valid():
            g = form.save()
            messages.success(request, "Gasto guardado.")
            return redirect(f"/finanzas/?mes={g.fecha:%Y-%m}")
    return render(request, "finanzas/gasto_formulario.html", {"form": form, "gasto": gasto})


@solo_propietaria
def pago_formulario(request, pk=None):
    pago = get_object_or_404(Pago, pk=pk) if pk else None
    form = PagoSueltoForm(request.POST or None, instance=pago)
    if request.method == "POST":
        if pago and "borrar" in request.POST:
            pago.delete()
            messages.success(request, "Ingreso eliminado.")
            return redirect("finanzas:resumen")
        if form.is_valid():
            p = form.save()
            messages.success(request, "Ingreso guardado.")
            return redirect(f"/finanzas/?mes={p.fecha:%Y-%m}")
    cliente_id = form["cliente"].value()
    cliente = Cliente.objects.filter(pk=cliente_id).first() if str(cliente_id or "").isdigit() else None
    return render(request, "finanzas/pago_formulario.html", {"form": form, "pago": pago, "cliente": cliente})


@solo_propietaria
@require_POST
def exportar(request):
    form = ExportarForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa las fechas de la exportación.")
        return redirect("finanzas:resumen")
    desde, hasta = form.cleaned_data["desde"], form.cleaned_data["hasta"]
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="movimientos-{desde:%Y%m%d}-{hasta:%Y%m%d}.csv"'
    n = servicios.escribir_csv(respuesta, desde, hasta)
    registrar(request, Accion.EXPORTACION, f"CSV de finanzas ({n} movimientos)", desde=str(desde), hasta=str(hasta))
    return respuesta
