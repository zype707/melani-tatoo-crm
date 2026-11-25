from django.core.management.base import BaseCommand

from apps.nucleo.exportacion import copia_de_seguridad


class Command(BaseCommand):
    help = (
        "Crea una copia de seguridad (datos JSON + archivos) en COPIAS_ROOT y conserva las "
        "COPIAS_A_CONSERVAR más recientes. Restaurar: ver README («Copias de seguridad»)."
    )

    def handle(self, *args, **opts):
        destino = copia_de_seguridad()
        self.stdout.write(self.style.SUCCESS(f"Copia creada: {destino} ({destino.stat().st_size // 1024} KB)"))
