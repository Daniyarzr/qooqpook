#!/bin/bash
TOKEN=$(sudo -u postgres psql -d qooq_vpn -t -A -c "SELECT subscription_token FROM subscriptions WHERE expires_at > now() ORDER BY id DESC LIMIT 1;")
echo TOKEN=$TOKEN
curl -sk -D /tmp/hdrs.txt "https://keys.qooqvpn.ru/sub/${TOKEN}" -o /tmp/sub.b64
echo "--- headers ---"
cat /tmp/hdrs.txt
echo "--- body first 120 chars ---"
head -c 120 /tmp/sub.b64; echo
echo "--- decoded first 400 chars ---"
base64 -d /tmp/sub.b64 2>/dev/null | head -c 400; echo
