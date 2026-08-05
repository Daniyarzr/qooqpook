#!/bin/bash
systemctl restart qooq-api
sleep 2
TOKEN=$(sudo -u postgres psql -d qooq_vpn -t -c "SELECT subscription_token FROM subscriptions ORDER BY id DESC LIMIT 1;" | tr -d ' ')
UUID=$(sudo -u postgres psql -d qooq_vpn -t -c "SELECT client_uuid FROM users ORDER BY id DESC LIMIT 1;" | tr -d ' ')
echo "TOKEN=$TOKEN"
echo "UUID=$UUID"
echo "=== /sub/{token} ==="
curl -sk -o /dev/null -w "status:%{http_code}\n" "https://keys.qooqvpn.ru/sub/${TOKEN}"
echo "=== /sub/{token}?format=json (uuid check) ==="
curl -sk "https://keys.qooqvpn.ru/sub/${TOKEN}?format=json" | grep -o '"id": "[^"]*"' | head -1
echo "=== old broken path ==="
curl -sk -o /dev/null -w "hub_only:%{http_code}\n" "https://keys.qooqvpn.ru/hub/sub/${TOKEN}"
