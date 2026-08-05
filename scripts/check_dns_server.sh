#!/bin/bash
apt-get install -y -qq dnsutils 2>/dev/null || true
echo "=== A records ==="
for d in keys.qooqvpn.ru admin.qooqvpn.ru app.qooqvpn.ru admin.keys.qooqvpn.ru app.keys.qooqvpn.ru qooqvpn.ru; do
  printf "%-28s " "$d:"
  host -t A "$d" 2>/dev/null | grep "has address" || host -t A "$d" 2>/dev/null | tail -1 || echo "NOT FOUND"
done
echo ""
echo "=== NS qooqvpn.ru ==="
host -t NS qooqvpn.ru 2>/dev/null
