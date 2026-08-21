"""Check Yandex nginx/xray health after failed Reality deploy."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    cmd = (
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'cat /etc/nginx/qooq_stream.conf; echo ---; sudo nginx -t; "
        "systemctl is-active nginx; systemctl is-active xray; "
        "ss -lntp | grep -E \"10443|18443|11443|:443\"'"
    )
    _, o, e = client.exec_command(cmd, timeout=60)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err[-2000:])
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
