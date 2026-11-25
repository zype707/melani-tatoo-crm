from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.nucleo.exportacion import exportar


class Command(BaseCommand):
    help = "Exporta todos los datos de negocio (sin credenciales) y los archivos a un .zip."

    def add_arguments(self, parser):
        parser.add_argument("--salida", default=f"exportacion-{timezone.localdate():%Y%m%d}.zip")
        parser.add_argument("--sin-archivos", action="store_true")

    def handle(self, *args, **opts):
        destino = Path(opts["salida"]).resolve()
        datos = exportar(destino, incluir_archivos=not opts["sin_archivos"])
        self.stdout.write(self.style.SUCCESS(f"Exportado en {destino} · {datos['archivos']} archivos"))
