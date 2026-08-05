#!/bin/bash
set -ex

# Port 80 MUST serve acme-challenge for ALL domains before HTTPS redirect
cat > /etc/nginx/sites-available/qooq-acme << 'EOF'
server {
    listen 80;
    server_name keys.qooqvpn.ru admin.qooqvpn.ru app.qooqvpn.ru;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
        allow all;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
EOF

# Keep existing HTTPS config or minimal keys-only https
if [ ! -f /etc/nginx/ssl/qooqvpn/fullchain.pem ]; then
  mkdir -p /etc/nginx/ssl/qooqvpn
  cp /etc/nginx/ssl/keys.qooqvpn.ru/fullchain.pem /etc/nginx/ssl/qooqvpn/fullchain.pem 2>/dev/null || true
  cp /etc/nginx/ssl/keys.qooqvpn.ru/key.pem /etc/nginx/ssl/qooqvpn/key.pem 2>/dev/null || true
fi

cat > /etc/nginx/sites-available/qooq-vpn << 'NGINXEOF'
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
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

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
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/qooq-acme /etc/nginx/sites-enabled/qooq-acme
ln -sf /etc/nginx/sites-available/qooq-vpn /etc/nginx/sites-enabled/qooq-vpn
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== Test port 80 acme path ==="
mkdir -p /var/www/html/.well-known/acme-challenge
echo ok > /var/www/html/.well-known/acme-challenge/test
curl -s -o /dev/null -w "keys80:%{http_code} " -H "Host: keys.qooqvpn.ru" http://127.0.0.1/.well-known/acme-challenge/test
curl -s -o /dev/null -w "app80:%{http_code} " -H "Host: app.qooqvpn.ru" http://127.0.0.1/.well-known/acme-challenge/test
curl -s -o /dev/null -w "admin80:%{http_code}\n" -H "Host: admin.qooqvpn.ru" http://127.0.0.1/.well-known/acme-challenge/test

echo "=== DNS from server ==="
host -t A app.qooqvpn.ru || true
host -t A admin.qooqvpn.ru || true

echo "=== Retry SSL ==="
ACME="/root/.acme.sh/acme.sh"
SSL_DIR="/etc/nginx/ssl/qooqvpn"
DOMAINS="-d keys.qooqvpn.ru"
host -t A app.qooqvpn.ru 2>/dev/null | grep -q "has address" && DOMAINS="$DOMAINS -d app.qooqvpn.ru"
host -t A admin.qooqvpn.ru 2>/dev/null | grep -q "has address" && DOMAINS="$DOMAINS -d admin.qooqvpn.ru"
echo "Issuing for: $DOMAINS"
$ACME --issue $DOMAINS -w /var/www/html --force && \
$ACME --install-cert -d keys.qooqvpn.ru \
  --key-file "${SSL_DIR}/key.pem" \
  --fullchain-file "${SSL_DIR}/fullchain.pem" \
  --reloadcmd "systemctl reload nginx" || echo "SSL issue failed - DNS may still be propagating"

nginx -t && systemctl reload nginx
systemctl restart qooq-bot
sleep 2

echo "=== Final ==="
systemctl is-active qooq-bot
curl -sk https://keys.qooqvpn.ru/health
echo
curl -sk -o /dev/null -w "app:%{http_code} panel:%{http_code}\n" https://app.qooqvpn.ru/ https://keys.qooqvpn.ru/panel/login
