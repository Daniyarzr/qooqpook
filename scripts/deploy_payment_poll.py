"""Deploy pending-payment poller + update cron."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/repositories/__init__.py",
    "src/services/payment.py",
    "scripts/poll_pending_payments.py",
]


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        sftp.put(str(PROJECT / rel), remote)
        print("uploaded", rel)

    cron = f"""*/5 * * * * root cd {REMOTE} && /usr/bin/flock -n /tmp/qooq-xray-sync.lock .venv/bin/python scripts/sync_xray_users.py >> /var/log/qooq-xray-sync.log 2>&1
*/5 * * * * root cd {REMOTE} && /usr/bin/flock -n /tmp/qooq-traffic-sync.lock .venv/bin/python scripts/sync_traffic.py >> /var/log/qooq-traffic-sync.log 2>&1
0 7 * * * root cd {REMOTE} && /usr/bin/flock -n /tmp/qooq-expiry.lock .venv/bin/python scripts/notify_subscription_expiry.py >> /var/log/qooq-expiry-reminders.log 2>&1
*/10 * * * * root cd {REMOTE} && /usr/bin/flock -n /tmp/qooq-payment-poll.lock /usr/bin/timeout 90 .venv/bin/python scripts/poll_pending_payments.py >> /var/log/qooq-payment-poll.log 2>&1
"""
    with sftp.file("/etc/cron.d/qooq-vpn", "w") as f:
        f.write(cron)
    sftp.chmod("/etc/cron.d/qooq-vpn", 0o644)
    sftp.close()

    def run(cmd: str, t: int = 90) -> int:
        _, o, e = client.exec_command(cmd, timeout=t)
        print(o.read().decode("utf-8", errors="replace"))
        err = e.read().decode("utf-8", errors="replace")
        if err.strip():
            print(err[-1500:])
        return o.channel.recv_exit_status()

    run("chmod 644 /etc/cron.d/qooq-vpn; cat /etc/cron.d/qooq-vpn")
    run(f"cd {REMOTE} && PYTHONPATH={REMOTE} .venv/bin/python scripts/poll_pending_payments.py")
    # restart api so payment service code is loaded for webhooks too
    run("systemctl restart qooq-api")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
