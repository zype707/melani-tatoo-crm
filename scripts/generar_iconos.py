"""Genera los iconos de la PWA (gota de tinta sobre bloque hueso, fondo petróleo).

Uso: python scripts/generar_iconos.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

PETROLEO = (6, 47, 56)
TINTA = (1, 22, 27)
HUESO = (244, 241, 232)
DESTINO = Path(__file__).resolve().parent.parent / "static" / "img"


def gota(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color):
    # Círculo inferior + triángulo superior = gota
    draw.ellipse([cx - r, cy - r * 0.2, cx + r, cy + r * 1.8], fill=color)
    draw.polygon([(cx, cy - r * 1.6), (cx - r * 0.93, cy + r * 0.45), (cx + r * 0.93, cy + r * 0.45)], fill=color)


def icono(tam: int, maskable: bool = False) -> Image.Image:
    escala = 4
    t = tam * escala
    img = Image.new("RGB", (t, t), PETROLEO)
    d = ImageDraw.Draw(img)
    margen = t * (0.2 if maskable else 0.12)
    lado = t - 2 * margen
    sombra = t * 0.045
    x0, y0 = margen - sombra / 2, margen - sombra / 2
    d.rectangle([x0 + sombra, y0 + sombra, x0 + lado + sombra, y0 + lado + sombra], fill=TINTA)
    d.rectangle([x0, y0, x0 + lado, y0 + lado], fill=HUESO, outline=TINTA, width=int(t * 0.025))
    gota(d, x0 + lado / 2, y0 + lado * 0.42, lado * 0.2, TINTA)
    return img.resize((tam, tam), Image.LANCZOS)


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    for tam in (180, 192, 512):
        icono(tam).save(DESTINO / f"icono-{tam}.png", optimize=True)
    icono(512, maskable=True).save(DESTINO / "icono-maskable-512.png", optimize=True)
    print("Iconos generados en", DESTINO)


if __name__ == "__main__":
    main()
