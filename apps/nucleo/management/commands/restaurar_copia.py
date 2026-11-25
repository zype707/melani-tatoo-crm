"""Restaura una copia creada por `copia_seguridad` (datos + archivos privados).

Pensado para dos situaciones: recuperar el estudio en un servidor nuevo, o volver
atrás tras un desastre. Sustituye TODOS los datos actuales por los de la copia,
incluida la cuenta y su 2FA (se entra con las credenciales que había en la copia).
"""

import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.clientes.models import Cliente


class Command(BaseCommand):
    help = "Restaura una copia de seguridad (.zip de copia_seguridad). Reemplaza todos los datos actuales."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta al .zip de la copia")
        parser.add_argument(
            "--sobrescribir", action="store_true", help="Necesario si la base de datos ya tiene clientes."
        )
        parser.add_argument("--si", action="store_true", help="No pedir confirmación.")

    def handle(self, *args, archivo, sobrescribir, si, **opts):
        ruta = Path(archivo)
        if not ruta.is_file() or not zipfile.is_zipfile(ruta):
            raise CommandError(f"{ruta} no es un .zip válido.")
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
            if "datos.json" not in nombres:
                raise CommandError("La copia no contiene datos.json: ¿es un archivo de copia_seguridad?")
            archivos = [n for n in nombres if n.startswith("archivos/") and not n.endswith("/")]
            for n in archivos:
                partes = PurePosixPath(n).parts
                if ".." in partes or n.startswith("/") or "\\" in n:
                    raise CommandError(f"Ruta sospechosa dentro del zip: {n}")

            if Cliente.objects.exists() and not sobrescribir:
                raise CommandError(
                    "La base de datos ya tiene clientes. Añade --sobrescribir si de verdad quieres reemplazarlos."
                )
            if not si:
                respuesta = input(
                    "Se borrarán TODOS los datos actuales y se cargará la copia. Escribe «restaurar» para seguir: "
                )
                if respuesta.strip().lower() != "restaurar":
                    raise CommandError("Cancelado.")

            with tempfile.TemporaryDirectory() as tmp:
                datos = Path(tmp) / "datos.json"
                datos.write_bytes(z.read("datos.json"))
                with transaction.atomic():
                    call_command("flush", interactive=False, verbosity=0)
                    call_command("loaddata", str(datos), verbosity=0)

            media = Path(settings.MEDIA_ROOT).resolve()
            for n in archivos:
                destino = (media / PurePosixPath(n).relative_to("archivos")).resolve()
                if not destino.is_relative_to(media):
                    raise CommandError(f"Ruta fuera de MEDIA_ROOT: {n}")
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(z.read(n))

        self.stdout.write(
            self.style.SUCCESS(
                f"Copia restaurada: {Cliente.objects.count()} clientes y {len(archivos)} archivos. "
                "Entra con la cuenta y el 2FA que había en la copia."
            )
        )
