#!/bin/bash
set -ex
ACME="/root/.acme.sh/acme.sh"
SSL_DIR="/etc/nginx/ssl/qooqvpn"

# Issue cert for domains that exist in DNS
DOMAINS="-d keys.qooqvpn.ru -d app.qooqvpn.ru"
if host -t A admin.qooqvpn.ru 2>/dev/null | grep -q "has address"; then
  DOMAINS="$DOMAINS -d admin.qooqvpn.ru"
  echo "admin.qooqvpn.ru found in DNS"
else
  echo "WARN: admin.qooqvpn.ru still missing - skipping from cert"
fi

$ACME --issue $DOMAINS -w /var/www/html --force

$ACME --install-cert -d keys.qooqvpn.ru \
  --key-file "${SSL_DIR}/key.pem" \
  --fullchain-file "${SSL_DIR}/fullchain.pem" \
  --reloadcmd "systemctl reload nginx"

cat > /etc/nginx/sites-available/qooq-vpn << 'NGINXEOF'
# keys.qooqvpn.ru — API + Hub + admin fallback /panel/
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

    location /panel/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# admin.qooqvpn.ru — Admin Panel (when DNS ready)
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

# app.qooqvpn.ru — Mini App
server {
    listen 443 ssl http2;
    server_name app.qooqvpn.ru;

    ssl_certificate /etc/nginx/ssl/qooqvpn/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/qooqvpn/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8000/miniapp;
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

server {
    listen 80;
    server_name keys.qooqvpn.ru admin.qooqvpn.ru app.qooqvpn.ru;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}
NGINXEOF

nginx -t && systemctl reload nginx
systemctl restart qooq-bot

echo "=== Results ==="
curl -sk -o /dev/null -w "keys:  %{http_code}\n"  https://keys.qooqvpn.ru/health
curl -sk -o /dev/null -w "app:   %{http_code}\n"  https://app.qooqvpn.ru/
curl -sk -o /dev/null -w "panel: %{http_code}\n" https://keys.qooqvpn.ru/panel/login
curl -sk -o /dev/null -w "admin: %{http_code}\n" https://admin.qooqvpn.ru/login 2>/dev/null || echo "admin: DNS missing"
systemctl is-active qooq-bot
