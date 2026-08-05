"""Final verification after Xray stats setup."""

import os
import sys

import paramiko

PANEL = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")


def run(c, cmd, timeout=60):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    code = o.channel.recv_exit_status()
    return code, o.read().decode("utf-8", errors="replace"), e.read().decode("utf-8", errors="replace")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(PANEL, username="root", password=PASSWORD, timeout=15)

    cmds = [
        "echo '=== DB traffic ==='",
        """sudo -u postgres psql -d qooq_vpn -c "SELECT s.id, s.user_id, s.status, round((s.bytes_upload+s.bytes_download)/1024.0/1024.0, 2) AS mb, s.last_traffic_sync_at FROM subscriptions s WHERE s.status IN ('active','trial') ORDER BY s.id;" """,
        "echo '=== Xray sync ==='",
        "cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py 2>&1 | tail -5",
        "echo '=== Sub feed test ==='",
        """TOKEN=$(sudo -u postgres psql -d qooq_vpn -t -A -c "SELECT subscription_token FROM subscriptions WHERE status IN ('active','trial') LIMIT 1;") && curl -sI "http://127.0.0.1:8000/sub/$TOKEN" | head -5""",
        "echo '=== Remote xray + clients ==='",
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 'systemctl is-active xray; ss -tlnp | grep -E \"443|10085\"'",
    ]
    for cmd in cmds:
        print(f"\n>>> {cmd[:70]}...")
        code, out, err = run(c, cmd)
        if out.strip():
            print(out.rstrip())
        if err.strip() and "Permission denied" not in err:
            print("ERR:", err.rstrip())
    c.close()


if __name__ == "__main__":
    main()
