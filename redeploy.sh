#!/usr/bin/env bash
# Incremental redeploy. Run on the server after pushing changes.

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

cd "${PROJECT_DIR}"
git pull --ff-only

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install -r requirements.txt

python manage.py migrate --noinput
python manage.py collectstatic --noinput

sudo systemctl restart "${GUNICORN_SERVICE}"
