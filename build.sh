#!/usr/bin/env bash
# Initial server-side setup for the hatchery deployment.
# Run from the Django project folder on the Ubuntu VPS droplet.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/../.venv"

# Create the production virtual environment if it does not already exist.
if [ ! -d "${VENV_DIR}" ]; then
    python3.12 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install -r "${PROJECT_DIR}/requirements.txt"

export DJANGO_SETTINGS_MODULE=hatchery.settings.prod

python "${PROJECT_DIR}/manage.py" migrate --noinput
python "${PROJECT_DIR}/manage.py" collectstatic --noinput

# Bring services up. Adjust the unit name to match the deployed systemd config.
sudo systemctl restart gunicorn-hatchery
