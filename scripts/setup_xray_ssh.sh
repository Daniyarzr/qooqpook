#!/bin/bash
# Generate SSH key on panel server for Xray sync to Yandex node.
set -euo pipefail

KEY_PATH="/root/.ssh/qooq_xray"
PUB_PATH="${KEY_PATH}.pub"
YANDEX_HOST="${1:-51.250.32.123}"
YANDEX_USER="${2:-adminka}"

if [[ ! -f "$KEY_PATH" ]]; then
  ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "qooq-xray-sync"
  echo "Created $KEY_PATH"
fi

echo
echo "=== Add this public key to $YANDEX_USER@$YANDEX_HOST ==="
echo "Run on Yandex server:"
echo
cat "$PUB_PATH"
echo
echo "mkdir -p ~/.ssh && chmod 700 ~/.ssh"
echo "echo 'PASTE_KEY_ABOVE' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
echo
echo "Then enable sync in /opt/qooq-vpn/.env:"
echo "XRAY_SYNC_ENABLED=true"
echo "XRAY_SSH_HOST=$YANDEX_HOST"
echo "XRAY_SSH_USER=$YANDEX_USER"
echo "XRAY_SSH_KEY_PATH=$KEY_PATH"
echo "XRAY_CONFIG_PATH=/usr/local/etc/xray/config.json"
echo "XRAY_INBOUND_PORT=443"
