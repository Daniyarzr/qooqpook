"""Restore missing telegram admin helpers and restart bot."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent

FILES = [
    "src/services/notifications.py",
    "src/bot/handlers/start.py",
    "src/admin/services.py",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
        print("uploaded", rel)
    sftp.close()

    def run(cmd: str, t: int = 90) -> str:
        _, o, e = client.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    print(
        run(
            "cd /opt/qooq-vpn && .venv/bin/python - <<'PY'\n"
            "from src.services.notifications import is_telegram_admin, notify_telegram_admins\n"
            "from src.bot.app import run_bot\n"
            "from src.admin.services import AdminService\n"
            "assert hasattr(AdminService, 'list_telegram_admins')\n"
            "print('import_ok')\n"
            "PY"
        )
    )
    print(run("systemctl restart qooq-bot qooq-api qooq-admin"))
    time.sleep(5)
    print("STATUS", run("systemctl is-active qooq-bot qooq-api qooq-admin"))
    print(run("journalctl -u qooq-bot -n 25 --no-pager"))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
