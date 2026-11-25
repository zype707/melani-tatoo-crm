from django.core.management.base import BaseCommand

from apps.nucleo.limpieza_archivos import borrar_huerfanos, limpiar_todo


class Command(BaseCommand):
    help = (
        "Borra archivos huérfanos (más de 24 h sin referencia en la BD), purga solicitudes rechazadas "
        "de más de 30 días y consentimientos de fichas anonimizadas fuera de plazo. Necesita el disco: "
        "en Render se lanza desde el cron con «disparar_tarea limpiar_archivos»."
    )

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="Solo cuenta los huérfanos, no borra nada.")

    def handle(self, *args, **opts):
        if opts["simular"]:
            self.stdout.write(f"Archivos huérfanos: {borrar_huerfanos(simular=True)}")
            return
        for clave, valor in limpiar_todo().items():
            self.stdout.write(f"  {clave}: {valor}")
        self.stdout.write(self.style.SUCCESS("Limpieza terminada."))
