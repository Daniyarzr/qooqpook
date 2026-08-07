"""Fix nginx proxy_pass for app.qooqvpn.ru (static assets 404)."""

import os
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")

FIX = r"""
set -ex
CONF=/etc/nginx/sites-available/qooq-vpn
sed -i 's|proxy_pass http://127.0.0.1:8000/miniapp;|proxy_pass http://127.0.0.1:8000/miniapp/;|g' "$CONF"
nginx -t
systemctl reload nginx
echo "=== verify ==="
curl -sk -o /dev/null -w 'app:%{http_code}\n' https://app.qooqvpn.ru/
curl -sk -o /dev/null -w 'css:%{http_code}\n' https://app.qooqvpn.ru/static/styles.css
curl -sk -o /dev/null -w 'js:%{http_code}\n' https://app.qooqvpn.ru/static/app.js
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    _, stdout, stderr = client.exec_command(FIX, timeout=30)
    print(stdout.read().decode("utf-8", errors="replace"))
    print(stderr.read().decode("utf-8", errors="replace"))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
