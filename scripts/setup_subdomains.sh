#!/bin/bash
# Setup 3 domains: keys / admin / app
set -ex

KEYS_DOMAIN="keys.qooqvpn.ru"
ADMIN_DOMAIN="admin.qooqvpn.ru"
APP_DOMAIN="app.qooqvpn.ru"
SSL_DIR="/etc/nginx/ssl/qooqvpn"

mkdir -p /var/www/html/.well-known/acme-challenge
mkdir -p "$SSL_DIR"

# ── Nginx HTTP (for cert challenge) ──
cat > /etc/nginx/sites-available/qooq-vpn << EOF
server {
    listen 80;
    server_name ${KEYS_DOMAIN} ${ADMIN_DOMAIN} ${APP_DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}
EOF
ln -sf /etc/nginx/sites-available/qooq-vpn /etc/nginx/sites-enabled/qooq-vpn
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── SSL certificate (all 3 domains) ──
ACME="/root/.acme.sh/acme.sh"
$ACME --issue \
  -d "${KEYS_DOMAIN}" \
  -d "${ADMIN_DOMAIN}" \
  -d "${APP_DOMAIN}" \
  -w /var/www/html --force 2>&1 | tail -10

$ACME --install-cert \
  -d "${KEYS_DOMAIN}" \
  --key-file "${SSL_DIR}/key.pem" \
  --fullchain-file "${SSL_DIR}/fullchain.pem" \
  --reloadcmd "systemctl reload nginx"

# ── HTTPS nginx ──
cat > /etc/nginx/sites-available/qooq-vpn << 'NGINXEOF'
# keys.qooqvpn.ru — API + Subscription Hub
server {
    listen 443 ssl http2;
    server_name keys.qooqvpn.ru;

    ssl_certificate /etc/nginx/ssl/qooqvpn/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/qooqvpn/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# admin.qooqvpn.ru — Admin Panel
server {
    listen 443 ssl http2;
    server_name admin.qooqvpn.ru;

    ssl_certificate /etc/nginx/ssl/qooqvpn/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/qooqvpn/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# app.qooqvpn.ru — Telegram Mini App
server {
    listen 443 ssl http2;
    server_name app.qooqvpn.ru;

    ssl_certificate /etc/nginx/ssl/qooqvpn/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/qooqvpn/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8000/miniapp/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINXEOF

nginx -t && systemctl reload nginx

# ── Update .env ──
ENV_FILE="/opt/qooq-vpn/.env"
sed -i "s|^HUB_DOMAIN=.*|HUB_DOMAIN=${KEYS_DOMAIN}|" "$ENV_FILE"
sed -i "s|^API_BASE_URL=.*|API_BASE_URL=https://${KEYS_DOMAIN}|" "$ENV_FILE"
sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://${APP_DOMAIN}|" "$ENV_FILE"
grep -q "^ADMIN_URL=" "$ENV_FILE" \
  && sed -i "s|^ADMIN_URL=.*|ADMIN_URL=https://${ADMIN_DOMAIN}|" "$ENV_FILE" \
  || echo "ADMIN_URL=https://${ADMIN_DOMAIN}" >> "$ENV_FILE"

systemctl restart qooq-api qooq-admin qooq-bot
sleep 3

echo "=== DNS records needed ==="
echo "  keys.qooqvpn.ru  A  148.135.184.188"
echo "  admin.qooqvpn.ru A  148.135.184.188"
echo "  app.qooqvpn.ru   A  148.135.184.188"
echo ""
echo "=== Status ==="
systemctl is-active qooq-api qooq-admin qooq-bot nginx
echo ""
echo "=== Health checks ==="
curl -sk -o /dev/null -w "keys:  %{http_code}\n" "https://${KEYS_DOMAIN}/health" || echo "keys: FAIL (DNS?)"
curl -sk -o /dev/null -w "admin: %{http_code}\n" "https://${ADMIN_DOMAIN}/login" || echo "admin: FAIL (DNS?)"
curl -sk -o /dev/null -w "app:   %{http_code}\n" "https://${APP_DOMAIN}/" || echo "app: FAIL (DNS?)"
