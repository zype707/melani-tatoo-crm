from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Búsqueda sin tildes («Maria» encuentra «María»)."""

    dependencies = [("nucleo", "0001_initial")]
    operations = [UnaccentExtension()]
