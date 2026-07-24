"""
Base settings shared across all environments.

Environment-specific overrides live in dev.py and prod.py and select which
file is loaded via the DJANGO_SETTINGS_MODULE environment variable.
"""

from pathlib import Path

import environ

# BASE_DIR points at the Django project folder (the one containing manage.py),
# i.e. .../hatchery_root/hatchery/. settings/base.py sits two parents below it.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# PROJECT_ROOT is one level above BASE_DIR (the repo-root container), where
# the external media/ directory and the universal venv live per rules.md §2.
PROJECT_ROOT = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# Read .env from the Django project folder if present. Production deploys
# place this file on the server; it is never committed.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-env")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# Application definition

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

LOCAL_APPS = [
    "core",
    "inventory",
    "sales",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hatchery.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "hatchery.wsgi.application"
ASGI_APPLICATION = "hatchery.asgi.application"


# Database — overridden per environment.
DATABASES = {}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Session — expire after 30 minutes of inactivity.
# SESSION_SAVE_EVERY_REQUEST resets the expiry window on every HTTP request so
# the clock measures inactivity, not total session age.
SESSION_COOKIE_AGE = 1800          # seconds (30 minutes)
SESSION_SAVE_EVERY_REQUEST = True


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static & media
# Static source files live in the global static/ directory at the project root
# (rules.md §2). collectstatic gathers them into STATIC_ROOT in production.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded media is stored outside the codebase (rules.md §2, §12).
MEDIA_URL = "/media/"
MEDIA_ROOT = PROJECT_ROOT / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Authentication routing
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:login"


# ────────────────────────────────────────────────────────────────────────
# Logging — production-grade configuration that captures errors to both
# a persistent file AND stderr (where Gunicorn picks them up).
#
# The Gunicorn systemd service already writes stderr to
# /var/log/gunicorn-hatchery-error.log via --error-logfile, so any log
# record that reaches stderr will end up in that file as well.
#
# Additionally we write directly to /var/log/django-hatchery.log so you
# have a clean Django-only audit trail separate from Gunicorn's own logs.
# ────────────────────────────────────────────────────────────────────────

# Path for the Django application log file.
DJANGO_LOG_DIR = Path("/var/log")
DJANGO_LOG_FILE = DJANGO_LOG_DIR / "django-hatchery.log"

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
        "traceback": {
            "format": "{levelname} {asctime} {message}\n{exc_info}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        # Writes to stderr — always active. Gunicorn captures stderr into
        # /var/log/gunicorn-hatchery-error.log.  This is the quickest way
        # to see errors via "sudo journalctl -u gunicorn-hatchery -f".
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "verbose",
        },
        # Writes to a persistent Django-specific file.  In production the
        # file is created by build.sh (or manually) with hatchery ownership.
        # This survives Gunicorn restarts and log rotations.
        "django_file": {
            "level": "ERROR",
            "class": "logging.handlers.WatchedFileHandler",
            "filename": str(DJANGO_LOG_FILE),
            "formatter": "verbose",
        },
        # Separate file handler that catches *everything* at WARNING+
        # for operational awareness (e.g. 404s, permission denials).
        "django_file_warn": {
            "level": "WARNING",
            "class": "logging.handlers.WatchedFileHandler",
            "filename": str(DJANGO_LOG_FILE),
            "formatter": "verbose",
        },
        # Email admins on production-critical errors (requires ADMINS setting).
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
            "handlers": ["console", "django_file"],
            "propagate": False,
        },
        # ── Django server logger ─────────────────────────────────────
        # Covers the runserver / WSGI / ASGI layer.
        "django.server": {
            "level": "ERROR",
            "handlers": ["console", "django_file"],
            "propagate": False,
        },
        # ── django.db.backends ───────────────────────────────────────
        # Uncomment temporarily to debug slow / failing SQL queries.
        # "django.db.backends": {
        #     "level": "WARNING",
        #     "handlers": ["console"],
        #     "propagate": False,
        # },
        # ── django.security ──────────────────────────────────────────
        # Covers SuspiciousOperation and related security events.
        "django.security": {
            "level": "WARNING",
            "handlers": ["console", "django_file_warn"],
            "propagate": False,
        },
        # ── Application-level loggers ────────────────────────────────
        # You can use  import logging; logger = logging.getLogger(__name__)
        # in any view / model / utility to emit messages here.
        "core": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
        "inventory": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
        "sales": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}