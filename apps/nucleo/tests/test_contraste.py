import importlib.util
from pathlib import Path


def test_paleta_cumple_wcag_aa():
    ruta = Path(__file__).resolve().parents[3] / "scripts" / "contraste.py"
    spec = importlib.util.spec_from_file_location("contraste", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    for texto, fondo, minimo in modulo.PARES:
        assert modulo.contraste(modulo.PALETA[texto], modulo.PALETA[fondo]) >= minimo, (texto, fondo)
