import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

TAREAS = ["limpiar_archivos", "copia_seguridad"]


class Command(BaseCommand):
    help = (
        "Pide al web service que ejecute una tarea que necesita el disco persistente. "
        "Lo usan los cron jobs de Render, que no pueden montar el disco."
    )

    def add_arguments(self, parser):
        parser.add_argument("tarea", choices=TAREAS)

    def handle(self, *args, **opts):
        if len(settings.TAREAS_SECRETO or "") < 32:
            raise CommandError("TAREAS_SECRETO no está configurado (mín. 32 caracteres).")
        url = f"{settings.SITE_URL}/interno/tareas/{opts['tarea']}/"
        peticion = urllib.request.Request(  # noqa: S310 - URL propia, configurada por entorno
            url, data=b"", method="POST", headers={"Authorization": f"Bearer {settings.TAREAS_SECRETO}"}
        )
        try:
            with urllib.request.urlopen(peticion, timeout=600) as r:  # noqa: S310
                datos = json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            raise CommandError(f"El servidor respondió {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise CommandError(f"No se pudo contactar con {url}: {exc.reason}") from exc
        self.stdout.write(self.style.SUCCESS(f"{opts['tarea']}: {datos}"))
