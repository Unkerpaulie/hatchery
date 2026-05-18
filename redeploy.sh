#!/usr/bin/env bash
# Incremental redeploy. Run on the server after pushing changes.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/../.venv"

cd "${PROJECT_DIR}"
git pull --ff-only

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install -r requirements.txt

export DJANGO_SETTINGS_MODULE=hatchery.settings.prod

python manage.py migrate --noinput
python manage.py collectstatic --noinput

sudo systemctl restart gunicorn-hatchery
