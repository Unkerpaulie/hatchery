#!/usr/bin/env bash
# Initial server-side setup for the hatchery deployment.
# Run from the Django project folder on the Ubuntu VPS droplet.

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

# Read the Gunicorn service name from .env so each app on the server can differ.
GUNICORN_SERVICE="${GUNICORN_SERVICE_NAME:-gunicorn-hatchery}"

# Create the production virtual environment if it does not already exist.
if [ ! -d "${VENV_DIR}" ]; then
    python3.12 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install -r "${PROJECT_DIR}/requirements.txt"

python "${PROJECT_DIR}/manage.py" migrate --noinput
python "${PROJECT_DIR}/manage.py" collectstatic --noinput

sudo systemctl restart "${GUNICORN_SERVICE}"
