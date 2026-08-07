"""Verify JSON configs admin deploy on production."""

import os
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    commands = [
        "systemctl is-active qooq-api qooq-admin qooq-bot",
        'curl -s -o /dev/null -w "admin_configs:%{http_code}" http://127.0.0.1:8001/configs',
        'curl -s -o /dev/null -w "admin_login:%{http_code}" http://127.0.0.1:8001/login',
        'sudo -u postgres psql -d qooq_vpn -c "SELECT id, name, config_type, is_default, is_active, server_id FROM vpn_configs ORDER BY id;"',
        "journalctl -u qooq-admin -n 8 --no-pager",
    ]

    for cmd in commands:
        print(">>>", cmd)
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        if out:
            print(out)
        if err:
            print("ERR", err)

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
