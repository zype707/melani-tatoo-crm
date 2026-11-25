"""Geometría de gráficos de barras en SVG (sin librerías externas).

Las vistas calculan aquí la posición de cada barra y la plantilla
`componentes/grafico_barras.html` solo dibuja. Una sola escala (nunca dos
ejes), base en cero, barras finas con separación y rejilla discreta.
"""

import math
from decimal import Decimal


def _paso_bonito(maximo: float, marcas: int = 4) -> float:
    if maximo <= 0:
        return 1
    bruto = maximo / marcas
    magnitud = 10 ** math.floor(math.log10(bruto))
    for factor in (1, 2, 2.5, 5, 10):
        if bruto <= factor * magnitud:
            return factor * magnitud
    return 10 * magnitud


def barras(etiquetas: list[str], series: list[dict], *, ancho: int = 640, alto: int = 220, resaltar: int | None = None):
    """series = [{"nombre": "Ingresos", "valores": [..], "clase": "serie-a"}, ...]"""
    margen_izq, margen_der, margen_sup, margen_inf = 56, 8, 12, 28
    area_w = ancho - margen_izq - margen_der
    area_h = alto - margen_sup - margen_inf
    maximo = max([float(v or 0) for s in series for v in s["valores"]] + [0])
    paso = _paso_bonito(maximo)
    tope = paso * max(1, math.ceil(maximo / paso)) if maximo else paso * 4
    n = max(1, len(etiquetas))
    grupo_w = area_w / n
    hueco = 2  # separación entre barras del mismo grupo
    barra_w = max(4.0, min(28.0, (grupo_w * 0.62 - hueco * (len(series) - 1)) / max(1, len(series))))
    base_y = margen_sup + area_h

    grupos = []
    for i, etiqueta in enumerate(etiquetas):
        total_w = barra_w * len(series) + hueco * (len(series) - 1)
        x0 = margen_izq + i * grupo_w + (grupo_w - total_w) / 2
        barras_grupo = []
        for j, s in enumerate(series):
            valor = s["valores"][i] or 0
            h = (float(valor) / tope) * area_h if tope else 0
            barras_grupo.append(
                {
                    "x": round(x0 + j * (barra_w + hueco), 2),
                    "y": round(base_y - h, 2),
                    "ancho": round(barra_w, 2),
                    "alto": round(max(h, 0), 2),
                    "valor": Decimal(str(valor)),
                    "clase": s.get("clase", ""),
                    "nombre": s["nombre"],
                }
            )
        grupos.append(
            {
                "etiqueta": etiqueta,
                "x": round(margen_izq + i * grupo_w + grupo_w / 2, 2),
                "barras": barras_grupo,
                "resaltado": i == resaltar,
            }
        )
    lineas = []
    valor = 0.0
    while valor <= tope + 1e-9:
        lineas.append({"y": round(base_y - (valor / tope) * area_h, 2), "valor": Decimal(str(round(valor, 2)))})
        valor += paso
    return {
        "ancho": ancho,
        "alto": alto,
        "base_y": base_y,
        "izq": margen_izq,
        "der": ancho - margen_der,
        "grupos": grupos,
        "lineas": lineas,
        "series": series,
        "etiqueta_y": alto - 8,
    }
