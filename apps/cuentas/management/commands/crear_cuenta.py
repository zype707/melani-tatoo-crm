import getpass
import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cuentas import servicios
from apps.cuentas.models import Usuario


class Command(BaseCommand):
    help = (
        "Crea una cuenta de acceso (usuario + contraseña). No hay registro público: "
        "las cuentas solo se crean con este comando."
    )

    def add_arguments(self, parser):
        parser.add_argument("--usuario", help="Nombre de usuario para entrar (sin espacios).")
        parser.add_argument("--nombre", default="", help="Nombre que se muestra en la app.")
        parser.add_argument("--rol", choices=[r.value for r in Usuario.Rol], default=Usuario.Rol.PROPIETARIA)
        parser.add_argument(
            "--password-env",
            metavar="VARIABLE",
            help="Lee la contraseña de esta variable de entorno (modo no interactivo).",
        )
        parser.add_argument(
            "--desde-entorno",
            action="store_true",
            help=(
                f"Crea la cuenta de la propietaria con {servicios.ENV_USUARIO}, {servicios.ENV_PASSWORD} "
                f"y {servicios.ENV_NOMBRE} (opcional). No hace nada si están vacías o si la cuenta ya existe. "
                "Pensado para el pre-deploy de Render."
            ),
        )

    def handle(self, *args, **opts):
        if opts["desde_entorno"]:
            return self._desde_entorno()
        if not opts["usuario"]:
            raise CommandError("Indica --usuario (o usa --desde-entorno).")

        if opts["password_env"]:
            password = os.environ.get(opts["password_env"], "")
            if not password:
                raise CommandError(f"La variable {opts['password_env']} está vacía.")
        else:
            password = getpass.getpass("Contraseña (mín. 12 caracteres): ")
            if password != getpass.getpass("Repite la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")

        cuenta = self._crear(opts["usuario"], password, opts["nombre"], opts["rol"])
        self.stdout.write(self.style.SUCCESS(f"Cuenta creada: {cuenta.usuario} ({cuenta.get_rol_display()})."))
        self.stdout.write("Ya puedes entrar en /acceso/ con ese usuario y contraseña.")

    def _desde_entorno(self):
        datos = servicios.datos_cuenta_inicial()
        if not datos["usuario"]:
            if not Usuario.objects.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"No hay ninguna cuenta y {servicios.ENV_USUARIO} está vacía: nadie puede entrar todavía."
                    )
                )
            return
        if Usuario.objects.filter(usuario__iexact=datos["usuario"]).exists():
            self.stdout.write(f"La cuenta «{datos['usuario']}» ya existe: no se modifica.")
            return
        if not datos["password"]:
            raise CommandError(f"{servicios.ENV_USUARIO} está definida pero {servicios.ENV_PASSWORD} está vacía.")
        cuenta = self._crear(datos["usuario"], datos["password"], datos["nombre"], Usuario.Rol.PROPIETARIA)
        self.stdout.write(self.style.SUCCESS(f"Cuenta de la propietaria creada: {cuenta.usuario}."))

    def _crear(self, usuario, password, nombre, rol) -> Usuario:
        try:
            return servicios.crear_cuenta(usuario, password, nombre=nombre, rol=rol)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
