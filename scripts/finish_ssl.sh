#!/bin/bash
# Run AFTER DNS A-records for admin.qooqvpn.ru and app.qooqvpn.ru are set
set -ex

ACME="/root/.acme.sh/acme.sh"
SSL_DIR="/etc/nginx/ssl/qooqvpn"

$ACME --issue \
  -d keys.qooqvpn.ru \
  -d admin.qooqvpn.ru \
  -d app.qooqvpn.ru \
  -w /var/www/html --force

$ACME --install-cert \
  -d keys.qooqvpn.ru \
  --key-file "${SSL_DIR}/key.pem" \
  --fullchain-file "${SSL_DIR}/fullchain.pem" \
  --reloadcmd "systemctl reload nginx"

nginx -t && systemctl reload nginx

echo "=== SSL issued for all domains ==="
curl -sk -o /dev/null -w "keys:  %{http_code}\n"  https://keys.qooqvpn.ru/health
curl -sk -o /dev/null -w "admin: %{http_code}\n" https://admin.qooqvpn.ru/login
curl -sk -o /dev/null -w "app:   %{http_code}\n" https://app.qooqvpn.ru/
