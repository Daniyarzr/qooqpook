"""Deploy production subscription expiry Telegram reminders."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent

FILES = [
    "src/services/expiry_reminders.py",
    "scripts/notify_subscription_expiry.py",
    "src/bot/handlers/start.py",
]


def ensure_dir(sftp: paramiko.SFTPClient, path: str) -> None:
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
        local = PROJECT / rel
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        sftp.put(str(local), remote)
        print("uploaded", rel)

    cron = f"""*/5 * * * * root cd {REMOTE} && .venv/bin/python scripts/sync_xray_users.py >> /var/log/qooq-xray-sync.log 2>&1
*/5 * * * * root cd {REMOTE} && .venv/bin/python scripts/sync_traffic.py >> /var/log/qooq-traffic-sync.log 2>&1
0 7 * * * root cd {REMOTE} && .venv/bin/python scripts/notify_subscription_expiry.py >> /var/log/qooq-expiry-reminders.log 2>&1
"""
    with sftp.file("/etc/cron.d/qooq-vpn", "w") as f:
        f.write(cron)
    sftp.chmod("/etc/cron.d/qooq-vpn", 0o644)
    sftp.close()

    def run(cmd: str, t: int = 90) -> tuple[int, str]:
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        text = out + (("\n" + err) if err.strip() else "")
        print(text)
        return code, text

    run("chmod 644 /etc/cron.d/qooq-vpn; cat /etc/cron.d/qooq-vpn")
    run("systemctl restart qooq-bot")
    time.sleep(3)
    # Dry-run once (sends only to users actually in 3/2/1-day window)
    code, out = run(f"cd {REMOTE} && .venv/bin/python scripts/notify_subscription_expiry.py")
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
