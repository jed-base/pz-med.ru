#!/bin/bash
set -euo pipefail

SITE_ROOT="${SITE_ROOT:-/var/www/pz-med.ru}"
OFFICE_ROOT="${OFFICE_ROOT:-/opt/pz-med-office}"
APP_DIR="$OFFICE_ROOT/app"
VENV="$OFFICE_ROOT/venv"
DATA_DIR="${OFFICE_DATA_DIR:-/var/lib/pz-med-office}"
ENV_FILE="/etc/pz-med-office.env"
SERVICE_FILE="/etc/systemd/system/pz-med-office.service"
NGINX_SNIPPET="/etc/nginx/snippets/pz-med-office.conf"
MAIN_NGINX_SITE="/etc/nginx/sites-available/pz-med.ru"
OFFICE_USER="pz-med-office"
PORT="${OFFICE_PORT:-5007}"
CREATED_CREDENTIALS=0
INITIAL_PASSWORD=""

if [[ $EUID -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

for command in python3 nginx systemctl; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

SOURCE="$SITE_ROOT/ops/office"
[[ -f "$SOURCE/office_app.py" ]] || { echo "Run pz-site-update first: office files are missing" >&2; exit 1; }
[[ -f "$SOURCE/requirements.txt" ]] || { echo "Office requirements are missing" >&2; exit 1; }
[[ -f "$MAIN_NGINX_SITE" ]] || { echo "Nginx site config not found: $MAIN_NGINX_SITE" >&2; exit 1; }

if ! id "$OFFICE_USER" >/dev/null 2>&1; then
  useradd --system --home /nonexistent --shell /usr/sbin/nologin "$OFFICE_USER"
fi

install -d -o root -g root -m 0755 "$OFFICE_ROOT" "$APP_DIR"
install -d -o "$OFFICE_USER" -g "$OFFICE_USER" -m 0750 "$DATA_DIR"

rm -rf "$APP_DIR"/*
cp -a "$SOURCE"/. "$APP_DIR"/
chown -R root:root "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 0755 {} +
find "$APP_DIR" -type f -exec chmod 0644 {} +
chmod 0755 "$APP_DIR/deploy_office.sh"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  CREATED_CREDENTIALS=1
  INITIAL_PASSWORD=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)
  SECRET_KEY=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
)
  PASSWORD_HASH=$("$VENV/bin/python" - "$INITIAL_PASSWORD" <<'PY'
import sys
from werkzeug.security import generate_password_hash
print(generate_password_hash(sys.argv[1]))
PY
)
  umask 077
  {
    printf 'SECRET_KEY=%s\n' "$SECRET_KEY"
    printf 'OFFICE_USERNAME=admin\n'
    printf 'OFFICE_PASSWORD_HASH=%s\n' "$PASSWORD_HASH"
    printf 'OFFICE_DB_PATH=%s/office.sqlite3\n' "$DATA_DIR"
  } > "$ENV_FILE"
fi
chown root:"$OFFICE_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=PZ-Med private delivery registry
After=network.target

[Service]
Type=simple
User=$OFFICE_USER
Group=$OFFICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/gunicorn --workers 2 --threads 2 --timeout 30 --bind 127.0.0.1:$PORT office_app:app
Restart=on-failure
RestartSec=3
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR
CapabilityBoundingSet=
LockPersonality=true

[Install]
WantedBy=multi-user.target
EOF

cat > "$NGINX_SNIPPET" <<EOF
location = /office {
    return 302 /office/;
}

location /office/ {
    proxy_pass http://127.0.0.1:$PORT;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host \$host;
    proxy_set_header X-Forwarded-Proto "https";
    proxy_set_header X-Forwarded-Protocol "";
    proxy_set_header X-Forwarded-SSL "";
    proxy_set_header Forwarded "";
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
    client_max_body_size 128k;
}
EOF

if ! grep -qF 'include /etc/nginx/snippets/pz-med-office.conf;' "$MAIN_NGINX_SITE"; then
  if grep -q 'charset utf-8;' "$MAIN_NGINX_SITE"; then
    sed -i '/charset utf-8;/a\    include /etc/nginx/snippets/pz-med-office.conf;' "$MAIN_NGINX_SITE"
  else
    echo "Could not find 'charset utf-8;' in $MAIN_NGINX_SITE; add this line inside pz-med.ru server block:" >&2
    echo "    include /etc/nginx/snippets/pz-med-office.conf;" >&2
    exit 1
  fi
fi

systemctl daemon-reload
systemctl enable pz-med-office.service
systemctl restart pz-med-office.service
nginx -t
systemctl reload nginx
sleep 2

echo "=== OFFICE SERVICE ==="
systemctl is-active pz-med-office.service

echo "=== LOCAL CHECK ==="
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -H 'Host: pz-med.ru' http://127.0.0.1/office/

echo
echo "PZ-Med office deployed: https://pz-med.ru/office/"
if [[ "$CREATED_CREDENTIALS" -eq 1 ]]; then
  echo
  echo "INITIAL CREDENTIALS (shown once):"
  echo "Login:    admin"
  echo "Password: $INITIAL_PASSWORD"
  echo "After first login, change the password on the 'Пароль' page."
else
  echo "Existing database and credentials were preserved."
fi
