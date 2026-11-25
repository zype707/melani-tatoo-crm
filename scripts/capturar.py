"""Herramienta de desarrollo: capturas de pantalla con Chrome headless.

Inicia sesión completa (contraseña + TOTP calculado desde la BD local) y
guarda capturas de las rutas indicadas. Requiere `pip install playwright` y
un Chrome instalado. No se usa en producción.

Uso:
  python scripts/capturar.py / /agenda/ --movil --escritorio
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "estudio.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # solo herramienta local

import django

django.setup()

from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import sync_playwright

BASE = os.environ.get("CAPTURA_BASE", "http://127.0.0.1:8000")
EMAIL = os.environ.get("CAPTURA_EMAIL", "vale@ejemplo.com")
CLAVE = os.environ.get("CAPTURA_CLAVE", "Tinta-Demo-2026!")
SALIDA = Path(os.environ.get("CAPTURA_SALIDA", "/tmp/capturas"))


def codigo_actual(confirmado=True) -> str:
    dispositivo = TOTPDevice.objects.filter(user__email=EMAIL, confirmed=confirmado).order_by("-id").first()
    # Evita reutilizar el mismo paso de tiempo (django-otp lo rechaza)
    while int(time.time()) // 30 <= dispositivo.last_t:
        time.sleep(1)
    return f"{totp(dispositivo.bin_key):06d}"


def entrar(pagina):
    pagina.goto(f"{BASE}/acceso/")
    pagina.fill("input[name=email]", EMAIL)
    pagina.fill("input[name=password]", CLAVE)
    pagina.click("button[type=submit]")
    pagina.wait_for_load_state("networkidle")
    if "/acceso/autenticadora/" in pagina.url:
        pagina.fill("input[name=codigo]", codigo_actual(confirmado=False))
        pagina.click("main form button[type=submit]")
        pagina.wait_for_load_state("networkidle")
        if "/acceso/codigos/" in pagina.url:
            pagina.click("main form button[type=submit]")
            pagina.wait_for_load_state("networkidle")
    elif "/acceso/verificar/" in pagina.url:
        pagina.fill("input[name=codigo]", codigo_actual())
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
