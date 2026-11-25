from django.core.management.base import BaseCommand

from apps.mensajeria.predeterminados import crear_predeterminados
from apps.nucleo.models import AjustesEstudio


class Command(BaseCommand):
    help = (
        "Crea el contenido inicial (plantillas, secuencia de cuidados, fechas destacadas de EE. UU., "
        "tipos de cita y horario). Solo actúa si aún no hay plantillas: es seguro en cada despliegue."
    )

    def handle(self, *args, **opts):
        AjustesEstudio.obtener()
        creado = crear_predeterminados()
        if any(creado.values()):
            self.stdout.write(self.style.SUCCESS(f"Contenido inicial creado: {creado}"))
        else:
            self.stdout.write("El estudio ya estaba inicializado.")
