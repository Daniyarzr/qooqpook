#!/bin/bash
host -t A app.qooqvpn.ru || true
host -t A admin.qooqvpn.ru || true
ACME=/root/.acme.sh/acme.sh
DOMAINS="-d keys.qooqvpn.ru"
host -t A app.qooqvpn.ru 2>/dev/null | grep -q "has address" && DOMAINS="$DOMAINS -d app.qooqvpn.ru" && echo "app OK"
host -t A admin.qooqvpn.ru 2>/dev/null | grep -q "has address" && DOMAINS="$DOMAINS -d admin.qooqvpn.ru" && echo "admin OK"
echo "Issuing: $DOMAINS"
$ACME --issue $DOMAINS -w /var/www/html --force 2>&1 | tail -10
$ACME --install-cert -d keys.qooqvpn.ru \
  --key-file /etc/nginx/ssl/qooqvpn/key.pem \
  --fullchain-file /etc/nginx/ssl/qooqvpn/fullchain.pem \
  --reloadcmd "systemctl reload nginx"
systemctl reload nginx
curl -sk https://keys.qooqvpn.ru/health; echo
curl -sk -o /dev/null -w "app:%{http_code} " https://app.qooqvpn.ru/
curl -sk -o /dev/null -w "panel:%{http_code}\n" https://keys.qooqvpn.ru/panel/login
