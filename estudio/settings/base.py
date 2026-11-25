"""Configuración común a todos los entornos.

Todo lo que cambia entre entornos se lee de variables de entorno (ver README,
sección «Variables de entorno»). Este módulo nunca contiene secretos reales.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(nombre: str, defecto: str | None = None) -> str | None:
    valor = os.environ.get(nombre)
    return valor if valor not in (None, "") else defecto


def env_bool(nombre: str, defecto: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None or valor == "":
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_int(nombre: str, defecto: int) -> int:
    try:
        return int(os.environ.get(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


def env_lista(nombre: str, defecto: str = "") -> list[str]:
    return [p.strip() for p in (env(nombre, defecto) or "").split(",") if p.strip()]


# --- Núcleo -----------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY", "")
DEBUG = False

ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS")
_render_host = env("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)

CSRF_TRUSTED_ORIGINS = env_lista("CSRF_TRUSTED_ORIGINS")

# URL pública absoluta, necesaria para los enlaces que viajan en los mensajes
# (los cron jobs no conocen la petición HTTP, así que no se puede deducir).
SITE_URL = (
    env("SITE_URL")
    or (f"https://{env('SITE_HOST')}" if env("SITE_HOST") else None)
    or env("RENDER_EXTERNAL_URL")
    or "http://localhost:8000"
).rstrip("/")
# El dominio de SITE_URL (p. ej. un dominio propio) queda autorizado sin configurar nada más.
_site_host = urlsplit(SITE_URL).hostname
if _site_host and _site_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_site_host)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.forms",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.nucleo",
    "apps.cuentas",
    "apps.clientes",
    "apps.agenda",
    "apps.mensajeria",
    "apps.finanzas",
    "apps.catalogo",
    "apps.ia",
    "apps.panel",
]

MIDDLEWARE = [
    "apps.nucleo.middleware.SaludMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "apps.nucleo.middleware.CabecerasSeguridadMiddleware",
    "apps.cuentas.middleware.AccesoVerificadoMiddleware",
]

ROOT_URLCONF = "estudio.urls"
WSGI_APPLICATION = "estudio.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
                "apps.nucleo.context_processors.estudio",
            ],
            "builtins": ["django.templatetags.static", "apps.nucleo.templatetags.ui"],
        },
    }
]

FORM_RENDERER = "apps.nucleo.formularios.Renderizador"

# --- Base de datos ----------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgres://estudio:estudio@localhost:5432/estudio",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_estudio",
    }
}

# --- Autenticación ----------------------------------------------------------

AUTH_USER_MODEL = "cuentas.Usuario"
AUTHENTICATION_BACKENDS = ["apps.cuentas.backends.BackendCorreosPermitidos"]
LOGIN_URL = "cuentas:login"

# Solo estos correos pueden entrar (separados por comas). El primero es la propietaria.
# Vacía = nadie puede entrar. Ver apps/cuentas/permitidos.py.
CORREOS_PERMITIDOS = [c.lower() for c in env_lista("CORREOS_PERMITIDOS")]
# Código secreto para crear la cuenta en el primer acceso (/acceso/alta/). Vacío = alta desactivada.
CODIGO_ALTA = env("CODIGO_ALTA", "")
LOGIN_REDIRECT_URL = "panel:inicio"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # Argon2id
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


def _emisor_totp(dispositivo):
    """Nombre que verá la usuaria en su app autenticadora."""
    from apps.nucleo.models import AjustesEstudio

    return AjustesEstudio.obtener().nombre or "Estudio"


OTP_TOTP_ISSUER = _emisor_totp
OTP_TOTP_THROTTLE_FACTOR = 1

# Bloqueo de acceso (ver apps/cuentas/servicios.py)
ACCESO_MAX_FALLOS_EMAIL_IP = env_int("ACCESO_MAX_FALLOS_EMAIL_IP", 5)
ACCESO_MAX_FALLOS_IP = env_int("ACCESO_MAX_FALLOS_IP", 20)
ACCESO_MAX_FALLOS_EMAIL = env_int("ACCESO_MAX_FALLOS_EMAIL", 30)
ACCESO_VENTANA_MINUTOS = env_int("ACCESO_VENTANA_MINUTOS", 15)
ACCESO_PREAUTH_MINUTOS = 10

# --- Sesiones y cookies ------------------------------------------------------

SESSION_COOKIE_NAME = "estudio_sesion"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("SESION_HORAS", 72) * 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "apps.nucleo.views.error_csrf"

# --- Seguridad ----------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# CSP: sin scripts ni estilos en línea. Solo se permiten atributos style=""
# (posiciones del calendario, colores de tipo de cita), que no ejecutan código.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "style-src-attr": [CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:", "blob:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "media-src": [CSP.SELF],
    "manifest-src": [CSP.SELF],
    "worker-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
}

# Número de proxies inversos de confianza delante de la app (Render = 1).
PROXIES_DE_CONFIANZA = env_int("PROXIES_DE_CONFIANZA", 0)

# Secreto compartido con los cron jobs para disparar tareas que necesitan el
# disco persistente (Render no permite montar el disco en un cron job).
TAREAS_SECRETO = env("TAREAS_SECRETO", "")

# --- Internacionalización ------------------------------------------------------

LANGUAGE_CODE = "es"
TIME_ZONE = env("TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True
FORMAT_MODULE_PATH = ["estudio.formatos"]
REGION_TELEFONO = env("REGION_TELEFONO", "US")
MONEDA = env("MONEDA", "USD")
SIMBOLO_MONEDA = env("SIMBOLO_MONEDA", "$")

# --- Estáticos y archivos privados ----------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Archivos subidos (fotos, firmas, consentimientos): NUNCA se sirven como
# estáticos. MEDIA_URL no está enrutado; se entregan con vistas autenticadas.
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media_privado")))
MEDIA_URL = "/no-publico/"
COPIAS_ROOT = Path(env("COPIAS_ROOT", str(BASE_DIR / "copias")))
COPIAS_A_CONSERVAR = env_int("COPIAS_A_CONSERVAR", 14)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 12
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

SUBIDAS_MAX_MB = env_int("SUBIDAS_MAX_MB", 8)
SUBIDAS_MAX_IMAGENES = env_int("SUBIDAS_MAX_IMAGENES", 5)

# --- IA (OpenAI) -------------------------------------------------------------------

OPENAI_API_KEY = env("OPENAI_API_KEY", "")
IA_MODELO = env("IA_MODELO", "gpt-6-luna")  # verifica el ID vigente en platform.openai.com/docs/models
IA_TIMEOUT_SEGUNDOS = env_int("IA_TIMEOUT_SEGUNDOS", 25)
IA_LIMITE_MENSUAL = env_int("IA_LIMITE_MENSUAL", 300)

# --- Registro --------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name}: {message}", "style": "{"}},
    "handlers": {"consola": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {"django.security": {"handlers": ["consola"], "level": "WARNING"}},
}
