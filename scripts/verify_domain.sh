#!/bin/bash
set -ex
curl -sk https://keys.qooqvpn.ru/health || true
echo
systemctl is-active qooq-bot qooq-api qooq-admin nginx
journalctl -u qooq-bot -n 6 --no-pager
grep -E 'HUB_DOMAIN|API_BASE|BOT_' /opt/qooq-vpn/.env
