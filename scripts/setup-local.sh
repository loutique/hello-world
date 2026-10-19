#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
path = Path('.env')
if not path.exists():
    path.write_text('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(48) + '\nDEBUG=1\nALLOWED_HOSTS=localhost,127.0.0.1,testserver\nPOSTGRES_DB=disco\nPOSTGRES_USER=disco\nPOSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\nPOSTGRES_HOST=db\nPOSTGRES_PORT=5432\n')
    path.chmod(0o600)
PY
export DOCKER_CONFIG="${DOCKER_CONFIG:-/workspace/docker-config}"
mkdir -p "$DOCKER_CONFIG"
PYTHON=.venv/bin/python scripts/build-offline.sh
docker compose up -d db
docker compose run --rm web python manage.py migrate --noinput
docker compose run --rm web python manage.py seed_campaign
