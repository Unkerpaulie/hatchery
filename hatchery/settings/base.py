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


