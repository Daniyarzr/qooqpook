"""Verify per-config UUID credentials on production."""

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
        "grep -E 'XRAY_SYNC_ENABLED|XRAY_SSH' /opt/qooq-vpn/.env",
        'sudo -u postgres psql -d qooq_vpn -c "SELECT COUNT(*) AS credentials FROM subscription_config_credentials WHERE revoked_at IS NULL;"',
        'sudo -u postgres psql -d qooq_vpn -c "SELECT c.name, c.config_type, COUNT(*) FROM subscription_config_credentials cred JOIN vpn_configs c ON c.id=cred.vpn_config_id WHERE cred.revoked_at IS NULL GROUP BY c.name, c.config_type ORDER BY c.id;"',
        "cd /opt/qooq-vpn && .venv/bin/python scripts/ensure_config_credentials.py",
        "cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py 2>&1 | tail -5",
    ]

    for cmd in commands:
        print(">>>", cmd)
        _, stdout, stderr = client.exec_command(cmd, timeout=60)
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
