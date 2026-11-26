"""Herramienta de desarrollo: capturas de pantalla con Chrome headless.

Inicia sesión con usuario y contraseña (CAPTURA_USUARIO / CAPTURA_CLAVE) y guarda
capturas de las rutas indicadas. Requiere `pip install playwright` y un Chrome
instalado. No se usa en producción.

Uso:
  python scripts/capturar.py / /agenda/ --movil --escritorio
"""

import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("CAPTURA_BASE", "http://127.0.0.1:8000")
USUARIO = os.environ.get("CAPTURA_USUARIO", "ink_mels")
CLAVE = os.environ.get("CAPTURA_CLAVE", "InkMels-Demo-2026!")
SALIDA = Path(os.environ.get("CAPTURA_SALIDA", "/tmp/capturas"))


def entrar(pagina):
    pagina.goto(f"{BASE}/acceso/")
    pagina.fill("input[name=usuario]", USUARIO)
    pagina.fill("input[name=password]", CLAVE)
    pagina.click("main form button[type=submit]")
    pagina.wait_for_load_state("networkidle")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rutas", nargs="*", default=["/"])
    parser.add_argument("--movil", action="store_true")
    parser.add_argument("--escritorio", action="store_true")
    parser.add_argument("--sin-sesion", action="store_true")
    parser.add_argument("--completa", action="store_true", help="Captura la página entera")
    args = parser.parse_args()
    tamanos = []
    if args.movil or not args.escritorio:
        tamanos.append(("movil", {"width": 390, "height": 844}))
    if args.escritorio:
        tamanos.append(("escritorio", {"width": 1366, "height": 900}))
    SALIDA.mkdir(parents=True, exist_ok=True)
    errores = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for nombre, tam in tamanos:
            contexto = navegador.new_context(viewport=tam, device_scale_factor=1, locale="es-US")
            pagina = contexto.new_page()
            pagina.on("console", lambda m: m.type == "error" and errores.append(m.text))
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            if not args.sin_sesion:
                entrar(pagina)
            for ruta in args.rutas:
                pagina.goto(f"{BASE}{ruta}")
                pagina.wait_for_load_state("networkidle")
                archivo = SALIDA / f"{nombre}{ruta.strip('/').replace('/', '_') or '_inicio'}.png"
                pagina.screenshot(path=str(archivo), full_page=args.completa)
                print(archivo)
            contexto.close()
        navegador.close()
    if errores:
        print("ERRORES DE CONSOLA:")
        for e in errores:
            print(" -", e)


if __name__ == "__main__":
    main()
