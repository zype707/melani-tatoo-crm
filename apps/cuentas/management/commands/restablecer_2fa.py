from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.cuentas.models import DispositivoRecuperacion, Usuario
from apps.nucleo.auditoria import Accion, registrar


class Command(BaseCommand):
    help = (
        "Elimina la app autenticadora y los códigos de recuperación de una cuenta. "
        "Úsalo solo si se perdió el móvil y los códigos. En el siguiente acceso se "
        "pedirá configurar la 2FA de nuevo."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--si", action="store_true", help="No pedir confirmación.")

    def handle(self, *args, **opts):
        usuario = Usuario.objects.filter(email__iexact=opts["email"]).first()
        if usuario is None:
            raise CommandError("No existe esa cuenta.")
        if not opts["si"] and input(f"¿Restablecer la 2FA de {usuario.email}? [s/N] ").lower() != "s":
            raise CommandError("Cancelado.")
        TOTPDevice.objects.filter(user=usuario).delete()
        DispositivoRecuperacion.objects.filter(user=usuario).delete()
        registrar(None, Accion.DOSFA_ACTIVADA, "2FA restablecida por comando", usuario=usuario)
        self.stdout.write(self.style.SUCCESS("2FA restablecida. Configúrala en el próximo acceso."))
