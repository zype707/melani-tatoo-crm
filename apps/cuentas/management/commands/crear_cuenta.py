import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cuentas.models import Usuario


class Command(BaseCommand):
    help = "Crea la cuenta de la tatuadora (no hay registro público)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nombre", default="")
        parser.add_argument("--rol", choices=[r.value for r in Usuario.Rol], default=Usuario.Rol.PROPIETARIA)
        parser.add_argument(
            "--password-env",
            metavar="VARIABLE",
            help="Lee la contraseña de esta variable de entorno (modo no interactivo).",
        )

    def handle(self, *args, **opts):
        email = opts["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Ya existe una cuenta con {email}.")

        if opts["password_env"]:
            password = os.environ.get(opts["password_env"], "")
            if not password:
                raise CommandError(f"La variable {opts['password_env']} está vacía.")
        else:
            password = getpass.getpass("Contraseña (mín. 12 caracteres): ")
            if password != getpass.getpass("Repite la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")

        nombre = opts["nombre"] or email.split("@")[0].capitalize()
        try:
            validate_password(password, Usuario(email=email, nombre=nombre))
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        Usuario.objects.create_user(email=email, password=password, nombre=nombre, rol=opts["rol"])
        self.stdout.write(self.style.SUCCESS(f"Cuenta creada para {email}."))
        self.stdout.write("Siguiente paso: entra en /acceso/ y configura la app autenticadora (2FA obligatoria).")
