#!/bin/bash
set -euo pipefail

SITE_ROOT="${SITE_ROOT:-/var/www/pz-med.ru}"
OFFICE_ROOT="${OFFICE_ROOT:-/opt/pz-med-office}"
APP_DIR="$OFFICE_ROOT/app"
VENV="$OFFICE_ROOT/venv"
DATA_DIR="${OFFICE_DATA_DIR:-/var/lib/pz-med-office}"
RELEASES_DIR="${OFFICE_RELEASES_DIR:-$DATA_DIR/releases}"
RELEASE_STATE_DIR="${PZ_MED_RELEASE_STATE_DIR:-/var/lib/pz-med-release}"
ENV_FILE="/etc/pz-med-office.env"
RELEASE_ENV_FILE="/etc/pz-med-office-release.env"
SERVICE_FILE="/etc/systemd/system/pz-med-office.service"
RELEASE_SERVICE_FILE="/etc/systemd/system/pz-med-office-release-worker.service"
NGINX_SNIPPET="/etc/nginx/snippets/pz-med-office.conf"
MAIN_NGINX_SITE="/etc/nginx/sites-available/pz-med.ru"
OFFICE_USER="pz-med-office"
PORT="${OFFICE_PORT:-5007}"
CREATED_CREDENTIALS=0
INITIAL_PASSWORD=""

CLINIC_RELEASE_SOURCE="${CLINIC_RELEASE_SOURCE:-/root/medical_cards/clinic_universal_stage2_test}"
CLINIC_RELEASE_PYTHON="${CLINIC_RELEASE_PYTHON:-$CLINIC_RELEASE_SOURCE/venv/bin/python}"
CLINIC_CUSTOMER_REGISTRY="${CLINIC_CUSTOMER_REGISTRY:-/root/.clinic-universal-release/customers}"
CLINIC_DELIVERY_ROOT="${CLINIC_DELIVERY_ROOT:-/root/clinic-universal-deliveries}"
CLINIC_RELEASE_SIGNING_KEY="${CLINIC_RELEASE_SIGNING_KEY:-/root/.clinic-universal-release/signing-private.pem}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

for command in python3 nginx systemctl git; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

SOURCE="$SITE_ROOT/ops/office"
[[ -f "$SOURCE/office_app.py" ]] || { echo "Run pz-site-update first: office files are missing" >&2; exit 1; }
[[ -f "$SOURCE/office_entry.py" ]] || { echo "Office release entrypoint is missing; run pz-site-update" >&2; exit 1; }
[[ -f "$SOURCE/release_worker.py" ]] || { echo "Office release worker is missing; run pz-site-update" >&2; exit 1; }
[[ -f "$SOURCE/requirements.txt" ]] || { echo "Office requirements are missing" >&2; exit 1; }
[[ -f "$MAIN_NGINX_SITE" ]] || { echo "Nginx site config not found: $MAIN_NGINX_SITE" >&2; exit 1; }

# Генерация поставок выполняется из отдельной рабочей копии PZ-Med.
[[ -d "$CLINIC_RELEASE_SOURCE/.git" ]] || {
  echo "PZ-Med release source is not a Git checkout: $CLINIC_RELEASE_SOURCE" >&2
  echo "Expected the stage2 test checkout. Run clinic-test-update first." >&2
  exit 1
}
[[ -f "$CLINIC_RELEASE_SOURCE/VERSION" ]] || {
  echo "VERSION is missing in $CLINIC_RELEASE_SOURCE; run clinic-test-update first." >&2
  exit 1
}
[[ -x "$CLINIC_RELEASE_PYTHON" ]] || {
  echo "Release Python is missing: $CLINIC_RELEASE_PYTHON" >&2
  echo "The release checkout must have its working venv." >&2
  exit 1
}
[[ -f "$CLINIC_RELEASE_SOURCE/scripts/office_customer_release.py" ]] || {
  echo "New release scripts are missing; run clinic-test-update first." >&2
  exit 1
}
[[ -f "$CLINIC_RELEASE_SOURCE/scripts/customer_update_release.py" ]] || {
  echo "New update release scripts are missing; run clinic-test-update first." >&2
  exit 1
}
[[ -f "$CLINIC_RELEASE_SIGNING_KEY" ]] || {
  echo "Private release signing key not found: $CLINIC_RELEASE_SIGNING_KEY" >&2
  echo "Do not generate a replacement if customer releases have already been signed with another key." >&2
  exit 1
}

if ! id "$OFFICE_USER" >/dev/null 2>&1; then
  useradd --system --home /nonexistent --shell /usr/sbin/nologin "$OFFICE_USER"
fi

install -d -o root -g root -m 0755 "$OFFICE_ROOT" "$APP_DIR"
install -d -o "$OFFICE_USER" -g "$OFFICE_USER" -m 0750 "$DATA_DIR" "$RELEASES_DIR"
install -d -o root -g root -m 0700 "$RELEASE_STATE_DIR" "$CLINIC_CUSTOMER_REGISTRY" "$CLINIC_DELIVERY_ROOT"

rm -rf "$APP_DIR"/*
cp -a "$SOURCE"/. "$APP_DIR"/
chown -R root:root "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 0755 {} +
find "$APP_DIR" -type f -exec chmod 0644 {} +
chmod 0755 "$APP_DIR/deploy_office.sh" "$APP_DIR/release_worker.py"

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
    printf 'OFFICE_RELEASES_DIR=%s\n' "$RELEASES_DIR"
  } > "$ENV_FILE"
else
  # Старые установки Office не содержали OFFICE_RELEASES_DIR.
  if ! grep -q '^OFFICE_RELEASES_DIR=' "$ENV_FILE"; then
    printf 'OFFICE_RELEASES_DIR=%s\n' "$RELEASES_DIR" >> "$ENV_FILE"
  fi
fi
chown root:"$OFFICE_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

# Этот EnvironmentFile читает только root-only release worker.
umask 077
cat > "$RELEASE_ENV_FILE" <<EOF
OFFICE_DB_PATH=$DATA_DIR/office.sqlite3
OFFICE_RELEASES_DIR=$RELEASES_DIR
CLINIC_RELEASE_SOURCE=$CLINIC_RELEASE_SOURCE
CLINIC_RELEASE_PYTHON=$CLINIC_RELEASE_PYTHON
CLINIC_CUSTOMER_REGISTRY=$CLINIC_CUSTOMER_REGISTRY
CLINIC_DELIVERY_ROOT=$CLINIC_DELIVERY_ROOT
CLINIC_RELEASE_SIGNING_KEY=$CLINIC_RELEASE_SIGNING_KEY
PZ_MED_RELEASE_STATE_DIR=$RELEASE_STATE_DIR
OFFICE_USER=$OFFICE_USER
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
PIP_NO_CACHE_DIR=1
EOF
chown root:root "$RELEASE_ENV_FILE"
chmod 0600 "$RELEASE_ENV_FILE"

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
ExecStart=$VENV/bin/gunicorn --workers 1 --threads 4 --timeout 30 --bind 127.0.0.1:$PORT office_entry:app
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

cat > "$RELEASE_SERVICE_FILE" <<EOF
[Unit]
Description=PZ-Med signed release worker
After=network.target pz-med-office.service

[Service]
Type=simple
User=root
Group=$OFFICE_USER
UMask=0007
WorkingDirectory=$APP_DIR
EnvironmentFile=$RELEASE_ENV_FILE
ExecStart=$VENV/bin/python $APP_DIR/release_worker.py
Restart=on-failure
RestartSec=4
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$DATA_DIR
ReadWritePaths=$RELEASE_STATE_DIR
ReadWritePaths=$CLINIC_CUSTOMER_REGISTRY
ReadWritePaths=$CLINIC_DELIVERY_ROOT

[Install]
WantedBy=multi-user.target
EOF

cat > "$NGINX_SNIPPET" <<EOF
location = /office {
    return 302 /office/;
}

# ^~ is intentional: the main public site has generic static-file locations.
# Without ^~ requests such as /office/static/office.css can be intercepted by
# those regex locations and the private office is rendered without CSS/JS.
location ^~ /office/ {
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

# Если старый worker когда-то оставил SQLite sidecar-файлы, возвращаем Office доступ.
for db_file in "$DATA_DIR"/office.sqlite3 "$DATA_DIR"/office.sqlite3-wal "$DATA_DIR"/office.sqlite3-shm; do
  if [[ -e "$db_file" ]]; then
    chown "$OFFICE_USER:$OFFICE_USER" "$db_file"
    chmod 0660 "$db_file" || true
  fi
done

systemctl daemon-reload
systemctl enable pz-med-office.service pz-med-office-release-worker.service
systemctl restart pz-med-office.service
systemctl restart pz-med-office-release-worker.service
nginx -t
systemctl reload nginx
sleep 3

echo "=== OFFICE SERVICE ==="
systemctl is-active pz-med-office.service

echo "=== RELEASE WORKER ==="
systemctl is-active pz-med-office-release-worker.service

echo "=== LOCAL CHECK ==="
curl -sS -o /dev/null -w 'Office:      HTTP %{http_code}\n' -H 'Host: pz-med.ru' http://127.0.0.1/office/
CSS_STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: pz-med.ru' http://127.0.0.1/office/static/office.css)
RELEASE_CSS_STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: pz-med.ru' http://127.0.0.1/office/static/release.css)
echo "Office CSS:  HTTP $CSS_STATUS"
echo "Release CSS: HTTP $RELEASE_CSS_STATUS"
if [[ "$CSS_STATUS" != "200" || "$RELEASE_CSS_STATUS" != "200" ]]; then
  echo "Office CSS is not being served correctly" >&2
  exit 1
fi

echo
echo "PZ-Med office deployed: https://pz-med.ru/office/"
echo "Release source: $CLINIC_RELEASE_SOURCE"
echo "Current source version: $(cat "$CLINIC_RELEASE_SOURCE/VERSION")"
echo "Current source commit:  $(git -C "$CLINIC_RELEASE_SOURCE" rev-parse --short=12 HEAD)"
if [[ "$CREATED_CREDENTIALS" -eq 1 ]]; then
  echo
  echo "INITIAL CREDENTIALS (shown once):"
  echo "Login:    admin"
  echo "Password: $INITIAL_PASSWORD"
  echo "After first login, change the password on the 'Пароль' page."
else
  echo "Existing database and credentials were preserved."
fi
