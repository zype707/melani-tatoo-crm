"""Tests: Postgres real (las restricciones de solape dependen de él)."""

import tempfile
from pathlib import Path

from .base import *

DEBUG = False
SECRET_KEY = "clave-de-tests-no-secreta-0123456789-abcdefghijklmnopqrstuvwxyz"
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = [
    # Argon2 con parámetros mínimos sería más lento; MD5 solo en tests.
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="estudio-media-test-"))
COPIAS_ROOT = Path(tempfile.mkdtemp(prefix="estudio-copias-test-"))
OPENAI_API_KEY = ""
TAREAS_SECRETO = "secreto-de-tests"
SITE_URL = "https://estudio.test"
CORREOS_PERMITIDOS = ["vale@ejemplo.com", "ayu@ejemplo.com", "ana@ejemplo.com", "b@ejemplo.com", "a@b.com"]
CODIGO_ALTA = "codigo-de-alta-de-tests-0123456789"
