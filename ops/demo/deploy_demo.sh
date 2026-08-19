#!/bin/bash
set -euo pipefail

CLINIC_SOURCE="${CLINIC_SOURCE:-/root/medical_cards/clinic_universal_stage2_test}"
SITE_ROOT="${SITE_ROOT:-/var/www/pz-med.ru}"
DEMO_ROOT="${DEMO_ROOT:-/opt/pz-med-demo}"
APP_DIR="$DEMO_ROOT/app"
VENV="$DEMO_ROOT/venv"
ENV_FILE="/etc/pz-med-demo.env"
SERVICE_FILE="/etc/systemd/system/pz-med-demo.service"
RESET_SERVICE_FILE="/etc/systemd/system/pz-med-demo-reset.service"
RESET_TIMER_FILE="/etc/systemd/system/pz-med-demo-reset.timer"
NGINX_SITE="/etc/nginx/sites-available/pz-med.ru"
NGINX_SNIPPET="/etc/nginx/snippets/pz-med-demo.conf"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

for command in git python3 nginx systemctl; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

[[ -d "$CLINIC_SOURCE/.git" ]] || { echo "Clinic Universal git checkout not found: $CLINIC_SOURCE" >&2; exit 1; }
[[ -f "$SITE_ROOT/ops/demo/demo_wsgi.py" ]] || { echo "Run pz-site-update first; demo ops files are missing" >&2; exit 1; }
[[ -f "$NGINX_SITE" ]] || { echo "Nginx site config not found: $NGINX_SITE" >&2; exit 1; }

mkdir -p "$DEMO_ROOT"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"

# Берём полноценный текущий код Clinic Universal, но без рабочей БД,
# пользовательских файлов и без изменения репозитория clinic-universal.
git -C "$CLINIC_SOURCE" archive --format=tar HEAD | tar -xf - -C "$APP_DIR"

cp "$SITE_ROOT/ops/demo/demo_wsgi.py" "$APP_DIR/demo_wsgi.py"
cp "$SITE_ROOT/ops/demo/seed_demo.py" "$APP_DIR/seed_demo.py"
cp "$SITE_ROOT/ops/demo/reset_demo.sh" /usr/local/sbin/pz-med-demo-reset
chmod 0755 /usr/local/sbin/pz-med-demo-reset "$APP_DIR/seed_demo.py"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  SECRET_KEY=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
)
  cat > "$ENV_FILE" <<EOF
SECRET_KEY=$SECRET_KEY
RELEASE_LICENSE_ENFORCED=0
TEMPLATE_CONVERTER_BINARY=/usr/bin/soffice
EOF
  chmod 0600 "$ENV_FILE"
fi

mkdir -p \
  "$APP_DIR/instance" \
  "$APP_DIR/generated" \
  "$APP_DIR/flask_session" \
  "$APP_DIR/app/static/branding"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$APP_DIR"
"$VENV/bin/flask" --app run.py db upgrade
"$VENV/bin/python" seed_demo.py

chown -R www-data:www-data \
  "$APP_DIR/instance" \
  "$APP_DIR/generated" \
  "$APP_DIR/flask_session" \
  "$APP_DIR/app/static/branding"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=PZ-Med public Clinic Universal demo
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/gunicorn --workers 2 --threads 2 --timeout 120 --bind 127.0.0.1:5006 demo_wsgi:application
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat > "$RESET_SERVICE_FILE" <<EOF
[Unit]
Description=Reset PZ-Med public demo database

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pz-med-demo-reset
EOF

cat > "$RESET_TIMER_FILE" <<EOF
[Unit]
Description=Hourly reset of PZ-Med public demo

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=90

[Install]
WantedBy=timers.target
EOF

cat > "$NGINX_SNIPPET" <<'EOF'
location = /demo {
    return 302 /demo/;
}

location /demo/ {
    proxy_pass http://127.0.0.1:5006;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Prefix /demo;
    client_max_body_size 2m;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
}
EOF

if ! grep -qF 'include /etc/nginx/snippets/pz-med-demo.conf;' "$NGINX_SITE"; then
  sed -i '/charset utf-8;/a\    include /etc/nginx/snippets/pz-med-demo.conf;' "$NGINX_SITE"
fi

systemctl daemon-reload
systemctl enable --now pz-med-demo.service
systemctl enable --now pz-med-demo-reset.timer

nginx -t
systemctl reload nginx

sleep 2

echo "=== DEMO SERVICE ==="
systemctl is-active pz-med-demo.service

echo "=== DEMO TIMER ==="
systemctl is-enabled pz-med-demo-reset.timer

echo "=== LOCAL HTTP CHECK ==="
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -H 'Host: pz-med.ru' http://127.0.0.1/demo/

echo
echo "Full Clinic Universal demo deployed."
echo "Open: https://pz-med.ru/demo/"
echo "Source commit: $(git -C "$CLINIC_SOURCE" rev-parse HEAD)"
