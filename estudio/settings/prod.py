"""Producción (Render)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import SECRET_KEY, SECURE_CSP, env_int

DEBUG = False

if not SECRET_KEY or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("SECRET_KEY no está definida o es demasiado corta.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^salud/$"]
SECURE_HSTS_SECONDS = env_int("HSTS_SEGUNDOS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True

SECURE_CSP = {**SECURE_CSP, "upgrade-insecure-requests": True}
PROXIES_DE_CONFIANZA = env_int("PROXIES_DE_CONFIANZA", 1)
