"""Verifica el contraste WCAG 2.x de los pares de color del sistema de diseño.

Uso: python scripts/contraste.py   (sale con código 1 si algún par de texto no llega a AA)
"""

import sys

PALETA = {
    "tinta": "#01161b",
    "petroleo-950": "#031f25",
    "petroleo-900": "#062f38",
    "petroleo-800": "#0b4250",
    "petroleo-700": "#12586a",
    "hueso": "#f4f1e8",
    "niebla": "#a8cbd2",
    "amarillo": "#ffe500",
}
# (texto, fondo, mínimo) · 4.5 = texto normal AA · 3 = texto grande / componentes
PARES = [
    ("hueso", "petroleo-900", 4.5),
    ("hueso", "petroleo-800", 4.5),
    ("hueso", "petroleo-700", 4.5),
    ("hueso", "tinta", 4.5),
    ("hueso", "petroleo-950", 4.5),
    ("niebla", "petroleo-900", 4.5),
    ("niebla", "petroleo-800", 4.5),
    ("niebla", "tinta", 4.5),
    ("tinta", "amarillo", 4.5),
    ("tinta", "hueso", 4.5),
    ("amarillo", "petroleo-900", 4.5),
    ("amarillo", "petroleo-800", 4.5),
    ("amarillo", "tinta", 4.5),
    ("niebla", "petroleo-950", 3.0),  # borde de campos de formulario (componente)
]


def luminancia(hexa: str) -> float:
    canales = [int(hexa[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main() -> int:
    fallos = 0
    for texto, fondo, minimo in PARES:
        r = contraste(PALETA[texto], PALETA[fondo])
        ok = r >= minimo
        fallos += not ok
        print(f"{'OK ' if ok else 'FALLA'} {texto:>13} sobre {fondo:<13} {r:5.2f}:1 (mín. {minimo})")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
