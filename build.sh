#!/usr/bin/env bash
# Initial server-side setup.  Run as a sudo-capable admin user from the
# Django project folder on the Ubuntu VPS droplet.
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

# Read the Gunicorn service name and app system user from .env.
GUNICORN_SERVICE="${GUNICORN_SERVICE_NAME:-gunicorn-hatchery}"
APP_USER="${APP_USER:-hatchery}"

# Ensure Gunicorn log files exist and are owned by the app user.
# /var/log is root-owned so only sudo can create files there.
for log_file in \
    "/var/log/${GUNICORN_SERVICE}-access.log" \
    "/var/log/${GUNICORN_SERVICE}-error.log"; do
    if [ ! -f "${log_file}" ]; then
        sudo touch "${log_file}"
        sudo chown "${APP_USER}:${APP_USER}" "${log_file}"
    fi
done

# Create the production virtual environment if it does not already exist.
if [ ! -d "${VENV_DIR}" ]; then
    sudo -H -u "${APP_USER}" python3.12 -m venv "${VENV_DIR}"
fi

sudo -H -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -H -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"

sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" migrate --noinput

sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" collectstatic --noinput

sudo systemctl restart "${GUNICORN_SERVICE}"
