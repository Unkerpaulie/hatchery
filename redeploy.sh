#!/usr/bin/env bash
# Incremental redeploy.  Run as a sudo-capable admin user after pushing changes.
# App-owned commands run as APP_USER; only the systemctl call needs plain sudo.
#
# Step order (rules.md §5):
#   1. pull          — fast-forward only; aborts if local changes exist
#   2. pip install   — installs any new/updated packages from requirements.txt
#   3. migrate       — applies pending migrations against the production DB
#   4. collectstatic — rebuilds the static-file manifest
#   5. test          — runs the full test suite; aborts deployment on failure
#   6. restart       — reloads Gunicorn only after every prior step succeeds
#
# Note on restart vs reload: `systemctl restart` does a cold restart (brief
# downtime, guaranteed clean state). `systemctl reload` sends SIGHUP for a
# graceful zero-downtime worker cycle, but requires ExecReload= to be
# configured in the systemd unit file. Use restart until the unit file is
# set up for graceful reload.
#
# Note on tests: Django creates a temporary `test_<DB_NAME>` database and
# destroys it after the run. The DB user in DATABASE_URL must have the
# PostgreSQL CREATEDB privilege for this to work.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/../.venv"

# ── Load .env ────────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

# ── Resolve settings module ──────────────────────────────────────────────────
DJANGO_ENV="${DJANGO_ENV:-production}"
if [ "${DJANGO_ENV}" = "production" ]; then
    export DJANGO_SETTINGS_MODULE="hatchery.settings.prod"
else
    export DJANGO_SETTINGS_MODULE="hatchery.settings.dev"
fi

GUNICORN_SERVICE="${GUNICORN_SERVICE_NAME:-gunicorn-hatchery}"
APP_USER="${APP_USER:-hatchery}"

# ── Ensure log file exists ───────────────────────────────────────────────────
DJANGO_LOG_FILE="${DJANGO_LOG_FILE:-/var/log/django-hatchery.log}"
if [ ! -f "${DJANGO_LOG_FILE}" ]; then
    sudo touch "${DJANGO_LOG_FILE}"
    sudo chown "${APP_USER}:${APP_USER}" "${DJANGO_LOG_FILE}"
fi

# ── Helper ───────────────────────────────────────────────────────────────────
step() { echo; echo "==> $*"; }

# ── 1. Pull ──────────────────────────────────────────────────────────────────
step "Pulling latest code (fast-forward only)"
sudo -H -u "${APP_USER}" git -C "${PROJECT_DIR}" pull --ff-only

# ── 2. Install dependencies ──────────────────────────────────────────────────
step "Installing Python dependencies"
sudo -H -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -q -r "${PROJECT_DIR}/requirements.txt"

# ── 3. Migrate ───────────────────────────────────────────────────────────────
step "Running database migrations"
sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" migrate --noinput

# ── 4. Collect static ────────────────────────────────────────────────────────
step "Collecting static files"
sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" collectstatic --noinput

# ── 5. Run tests ─────────────────────────────────────────────────────────────
# Runs against DJANGO_SETTINGS_MODULE using a temporary test database.
# set -e ensures a non-zero exit here aborts the script before Gunicorn restarts.
step "Running test suite"
if ! sudo -H -u "${APP_USER}" \
    env DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}" \
    "${VENV_DIR}/bin/python" "${PROJECT_DIR}/manage.py" test --noinput 2>&1; then
    echo
    echo "ERROR: Tests failed. Gunicorn has NOT been restarted." >&2
    echo "       Fix the failing tests before redeploying." >&2
    exit 1
fi

# ── 6. Restart Gunicorn ──────────────────────────────────────────────────────
step "Restarting Gunicorn (${GUNICORN_SERVICE})"
sudo systemctl restart "${GUNICORN_SERVICE}"

echo
echo "==> Deploy complete."
