"""Deploy broadcast feature — bot only restart."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent

FILES = [
    "src/bot/app.py",
    "src/bot/states.py",
    "src/bot/commands.py",
    "src/bot/keyboards/reply.py",
    "src/bot/keyboards/__init__.py",
    "src/bot/keyboards/inline.py",
    "src/bot/handlers/start.py",
    "src/bot/handlers/reply_menu.py",
    "src/bot/handlers/broadcast.py",
    "src/services/notifications.py",
    "src/repositories/__init__.py",
]


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def run(client, cmd, timeout=90):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for rel in FILES:
        if not (PROJECT / rel).exists():
            print("Missing", rel)
            return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, banner_timeout=30)

    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), remote)
    sftp.close()

    out, err, code = run(
        client,
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.bot.handlers import broadcast; from src.services.notifications import is_telegram_admin; "
        "from src.bot.app import create_bot; print('import_ok')\"",
    )
    print(out)
    if err:
        print(err)
    if "import_ok" not in out:
        print("ABORT")
        client.close()
        return 1

    out, err, _ = run(
        client,
        "systemctl restart qooq-bot && sleep 3 && systemctl is-active qooq-bot && "
        "journalctl -u qooq-bot --since '30 sec ago' --no-pager | tail -n 15",
    )
    print(out)
    if err:
        print(err)
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
