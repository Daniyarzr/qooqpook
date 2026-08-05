#!/bin/bash
set -ex
ACME=/root/.acme.sh/acme.sh
SSL_DIR=/etc/nginx/ssl/qooqvpn

# Check at authoritative REG.RU, NOT local 127.0.0.53
DOMAINS="-d keys.qooqvpn.ru"
for sub in app admin; do
  ip=$(dig +short ${sub}.qooqvpn.ru @ns1.reg.ru | tail -1)
  if [ "$ip" = "148.135.184.188" ]; then
    DOMAINS="$DOMAINS -d ${sub}.qooqvpn.ru"
    echo "OK: ${sub}.qooqvpn.ru -> $ip"
  else
    echo "MISSING: ${sub}.qooqvpn.ru (got: $ip)"
  fi
done

echo "Issuing cert for: $DOMAINS"
$ACME --issue $DOMAINS -w /var/www/html --force
$ACME --install-cert -d keys.qooqvpn.ru \
  --key-file "${SSL_DIR}/key.pem" \
  --fullchain-file "${SSL_DIR}/fullchain.pem" \
  --reloadcmd "systemctl reload nginx"
systemctl reload nginx

echo "=== Verify ==="
for d in keys.qooqvpn.ru app.qooqvpn.ru admin.qooqvpn.ru; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://${d}/" 2>/dev/null || echo "000")
  echo "$d -> HTTP $code"
done
curl -sk https://keys.qooqvpn.ru/health
echo
curl -sk -o /dev/null -w "admin_login:%{http_code}\n" https://admin.qooqvpn.ru/login
