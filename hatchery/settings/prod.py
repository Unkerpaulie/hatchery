"""Production settings for the Ubuntu VPS droplet deployment."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# Security hardening — defaults are prod-safe; override in .env only to debug.
SECURE_PROXY_SSL_HEADER        = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT            = env.bool("SECURE_SSL_REDIRECT",            default=True)
SESSION_COOKIE_SECURE          = env.bool("SESSION_COOKIE_SECURE",          default=True)
CSRF_COOKIE_SECURE             = env.bool("CSRF_COOKIE_SECURE",             default=True)
SECURE_HSTS_SECONDS            = env.int( "SECURE_HSTS_SECONDS",            default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD            = env.bool("SECURE_HSTS_PRELOAD",            default=True)

# WhiteNoise serves the compressed/hashed static manifest in production.
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ─── Error reporting ──────────────────────────────────────────────────────────
# When DEBUG=False, Django emails ERROR-level logs to these addresses via the
# mail_admins logging handler below.  Uncomment and set at least one email to
# receive tracebacks for every 500 error in production.
# ADMINS = [("Your Name", "you@example.com")]
# SERVER_EMAIL = "root@hatchery.islan.dev"

# ─── Logging ──────────────────────────────────────────────────────────────────
# File path for the Django application log file (read from .env).
# Example: DJANGO_LOG_FILE=/var/log/django-hatchery.log
DJANGO_LOG_FILE = env("DJANGO_LOG_FILE", default="/var/log/django-hatchery.log")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "{levelname} {asctime} {module} {process:d} {thread:d}  "
                "{message}"
            ),
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        # Writes to stderr — always active.  Gunicorn captures stderr into
        # /var/log/gunicorn-hatchery-error.log (see the systemd service file).
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "verbose",
        },
        # Writes to a persistent Django-specific file on disk.
        # build.sh and redeploy.sh ensure the file exists with correct ownership.
        "django_file": {
            "level": "ERROR",
            "class": "logging.handlers.WatchedFileHandler",
            "filename": DJANGO_LOG_FILE,
            "formatter": "verbose",
        },
        # Email admins on production-critical errors.
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "loggers": {
        # ── Root logger ──────────────────────────────────────────────
        # Catches anything not matched by a more specific logger below.
        "": {
            "level": "WARNING",
            "handlers": ["console"],
        },
        # ── Django request logger ────────────────────────────────────
        # This is the logger Django itself uses when DEBUG=False and a
        # view raises an unhandled exception.  You MUST see this output.
        "django.request": {
            "level": "ERROR",
            "handlers": ["console", "django_file", "mail_admins"],
            "propagate": False,
        },
        # ── Django server logger ─────────────────────────────────────
        # Covers the runserver / WSGI / ASGI layer.
        "django.server": {
            "level": "ERROR",
            "handlers": ["console", "django_file"],
            "propagate": False,
        },
        # ── django.security ──────────────────────────────────────────
        # Covers SuspiciousOperation and related security events.
        "django.security": {
            "level": "WARNING",
            "handlers": ["console", "django_file"],
            "propagate": False,
        },
    },
}