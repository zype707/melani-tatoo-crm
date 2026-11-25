from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from apps.mensajeria.generadores import ejecutar_diario
from apps.nucleo.limpieza import limpiar_base_de_datos


class Command(BaseCommand):
    help = (
        "Tarea diaria (cron): prepara la bandeja «Mensajes de hoy» (recordatorios, cuidados, "
        "cumpleaños, aniversarios, fechas destacadas, reactivaciones) y limpia datos caducados. "
        "Es idempotente: ejecutarla dos veces no duplica nada."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")
        parser.add_argument("--sin-limpieza", action="store_true")

    def handle(self, *args, **opts):
        hoy = parse_date(opts["fecha"]) if opts.get("fecha") else None
        resultado = ejecutar_diario(hoy)
        for clave, valor in resultado.items():
            self.stdout.write(f"  {clave}: {valor}")
        if not opts["sin_limpieza"]:
            for clave, valor in limpiar_base_de_datos().items():
                self.stdout.write(f"  limpieza.{clave}: {valor}")
        self.stdout.write(self.style.SUCCESS("Bandeja del día preparada."))
