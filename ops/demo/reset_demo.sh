#!/bin/bash
set -euo pipefail

DEMO_ROOT="${DEMO_ROOT:-/opt/pz-med-demo}"
APP_DIR="$DEMO_ROOT/app"
VENV="$DEMO_ROOT/venv"
SERVICE="pz-med-demo"
ENV_FILE="/etc/pz-med-demo.env"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

systemctl stop "$SERVICE" 2>/dev/null || true

rm -f "$APP_DIR/instance/universal.db"
mkdir -p "$APP_DIR/instance"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$APP_DIR"
"$VENV/bin/flask" --app run.py db upgrade
"$VENV/bin/python" seed_demo.py
"$VENV/bin/python" enrich_demo.py
"$VENV/bin/python" enrich_deferred_demo.py
"$VENV/bin/python" enrich_showcase_demo.py

chown -R www-data:www-data \
  "$APP_DIR/instance" \
  "$APP_DIR/generated" \
  "$APP_DIR/flask_session" \
  "$APP_DIR/app/static/branding" \
  2>/dev/null || true

systemctl start "$SERVICE"

echo "PZ-Med demo reset complete: $(date -Is)"