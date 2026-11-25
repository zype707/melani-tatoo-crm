"""Desarrollo local. Nunca usar en producción."""

from .base import *
from .base import env, env_lista

DEBUG = True
SECRET_KEY = env("SECRET_KEY", "solo-para-desarrollo-local-no-usar-en-produccion-0123456789")
ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
