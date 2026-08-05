#!/bin/bash
echo "=== SERVICES ==="
systemctl is-active qooq-bot qooq-api qooq-admin nginx

echo "=== BOT LOGS ==="
journalctl -u qooq-bot -n 40 --no-pager

echo "=== BOT ENV ==="
grep -E '^BOT_' /opt/qooq-vpn/.env | sed 's/BOT_TOKEN=.*/BOT_TOKEN=***/'

echo "=== PROCESS ==="
ps aux | grep run_bot | grep -v grep

echo "=== DNS ==="
dig +short admin.qooqvpn.ru A
dig +short app.qooqvpn.ru A
dig +short keys.qooqvpn.ru A

echo "=== SSL ==="
curl -sk -o /dev/null -w "keys:%{http_code} " https://keys.qooqvpn.ru/health
curl -sk -o /dev/null -w "admin:%{http_code} " https://admin.qooqvpn.ru/login
curl -sk -o /dev/null -w "app:%{http_code}\n" https://app.qooqvpn.ru/

echo "=== TEST BOT IMPORT ==="
cd /opt/qooq-vpn && timeout 8 .venv/bin/python run_bot.py 2>&1 | head -20 || true
