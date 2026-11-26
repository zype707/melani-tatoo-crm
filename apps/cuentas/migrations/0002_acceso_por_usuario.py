"""Del acceso por email + 2FA al acceso por usuario y contraseña.

- Cada cuenta existente recibe como usuario lo que había antes de la @ de su email
  (sin repetir: vale, vale2…). La contraseña no cambia.
- Se eliminan los códigos de recuperación y la tabla de django-otp (app retirada).
"""

import re

import django.contrib.auth.validators
import django.db.models.functions.text
from django.db import migrations, models


def email_a_usuario(apps, schema_editor):
    Usuario = apps.get_model("cuentas", "Usuario")
    ocupados = set()
    for cuenta in Usuario.objects.order_by("pk"):
        local = (cuenta.email or "").split("@")[0].strip().lower()
        base = re.sub(r"[^\w.@+-]", "", local)[:140] or f"usuaria{cuenta.pk}"
        candidato, n = base, 2
        while candidato in ocupados:
            candidato, n = f"{base}{n}", n + 1
        ocupados.add(candidato)
        cuenta.usuario = candidato
        cuenta.save(update_fields=["usuario"])


class Migration(migrations.Migration):
    dependencies = [
        ("cuentas", "0001_initial"),
    ]

    operations = [
        # --- Usuario: email → usuario -------------------------------------------------------
        migrations.AddField(
            model_name="usuario",
            name="usuario",
            field=models.CharField(max_length=150, null=True),
        ),
        migrations.RunPython(email_a_usuario, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="usuario",
            name="usuario",
            field=models.CharField(
                help_text="Letras, números y . _ - @ (sin espacios).",
                max_length=150,
                unique=True,
                validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                verbose_name="Usuario",
            ),
        ),
        migrations.RemoveConstraint(model_name="usuario", name="usuario_email_unico_ci"),
        migrations.RemoveField(model_name="usuario", name="email"),
        migrations.AddConstraint(
            model_name="usuario",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("usuario"), name="usuario_usuario_unico_ci"
            ),
        ),
        # --- Sin 2FA -------------------------------------------------------------------------
        migrations.DeleteModel(name="CodigoRecuperacion"),
        migrations.DeleteModel(name="DispositivoRecuperacion"),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS otp_totp_totpdevice CASCADE; DELETE FROM django_migrations WHERE app = 'otp_totp';",
            migrations.RunSQL.noop,
        ),
        # --- Intentos de acceso: email → usuario, sin fase de 2FA ----------------------------
        migrations.RemoveIndex(model_name="intentoacceso", name="cuentas_int_email_60b7ae_idx"),
        migrations.RenameField(model_name="intentoacceso", old_name="email", new_name="usuario"),
        migrations.RunSQL("UPDATE cuentas_intentoacceso SET usuario = LEFT(usuario, 150);", migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="intentoacceso",
            name="usuario",
            field=models.CharField(max_length=150),
        ),
        migrations.RemoveField(model_name="intentoacceso", name="fase"),
        migrations.AddIndex(
            model_name="intentoacceso",
            index=models.Index(fields=["usuario", "creado_en"], name="cuentas_int_usuario_073ef8_idx"),
        ),
    ]
