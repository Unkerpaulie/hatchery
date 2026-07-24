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
# mail_admins logging handler (configured in base.py).  Set at least one email
# to receive tracebacks for every 500 error in production.
# ADMINS = [("Your Name", "you@example.com")]
# SERVER_EMAIL = "root@hatchery.islan.dev"   # sender address for those emails
