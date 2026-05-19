#!/usr/bin/env bash
# Incremental redeploy.  Run as a sudo-capable admin user after pushing changes.
# App-owned commands run as APP_USER; only the systemctl call needs plain sudo.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/../.venv"

# Load variables from .env so scripts share the same config as Django.
# shellcheck disable=SC1091
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

# Derive the Django settings module from DJANGO_ENV (default: production).
DJANGO_ENV="${DJANGO_ENV:-production}"
if [ "${DJANGO_ENV}" = "production" ]; then
    export DJANGO_SETTINGS_MODULE="hatchery.settings.prod"
else
    export DJANGO_SETTINGS_MODULE="hatchery.settings.dev"
fi

GUNICORN_SERVICE="${GUNICORN_SERVICE_NAME:-gunicorn-hatchery}"
APP_USER="${APP_USER:-hatchery}"

sudo -H -u "${APP_USER}" git -C "${PROJECT_DIR}" pull --ff-only

sudo -H -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"

sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" migrate --noinput

sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" collectstatic --noinput

sudo systemctl restart "${GUNICORN_SERVICE}"
