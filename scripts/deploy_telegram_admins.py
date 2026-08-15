"""Deploy telegram-admins + bot menu changes. Runs alembic, restarts services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD environment variable")

REMOTE_ROOT = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent

FILES = [
    "alembic/versions/013_telegram_admins.py",
    "alembic/env.py",
    "src/models/__init__.py",
    "src/services/notifications.py",
    "src/services/payment.py",
    "src/bot/app.py",
    "src/bot/commands.py",
    "src/bot/keyboards/__init__.py",
    "src/bot/keyboards/reply.py",
    "src/bot/handlers/start.py",
    "src/bot/handlers/reply_menu.py",
    "src/bot/handlers/subscription.py",
    "src/admin/app.py",
    "src/admin/services.py",
    "src/admin/templates/base.html",
    "src/admin/templates/telegram_admins.html",
    "src/api/routes/miniapp_api.py",
]


def ensure_remote_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[str, str, int]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    for rel in FILES:
        if not (PROJECT / rel).exists():
            print(f"Missing local file: {rel}")
            return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, banner_timeout=30)

    out, err, _ = run(client, "systemctl is-active qooq-bot qooq-api qooq-admin")
    print("PREFLIGHT:\n" + out)

    sftp = client.open_sftp()
    for rel in FILES:
        local = PROJECT / rel
        remote = f"{REMOTE_ROOT}/{rel}"
        ensure_remote_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print(f"Upload {rel}")
        sftp.put(str(local), remote)
    sftp.close()

    out, err, code = run(
        client,
        "cd /opt/qooq-vpn && .venv/bin/alembic upgrade head",
        timeout=180,
    )
    print("ALEMBIC:\n" + out)
    if err:
        print("ALEMBIC STDERR:\n" + err)
    if code != 0:
        print("ABORT: migration failed")
        client.close()
        return 1

    out, err, code = run(
        client,
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.models import TelegramAdmin; "
        "from src.services.notifications import notify_telegram_admins; "
        "from src.bot.commands import setup_bot_commands; "
        "from src.bot.keyboards.reply import BTN_MAIN_MENU, main_reply_keyboard; "
        "from src.admin.app import create_admin_app; "
        "print('import_ok', BTN_MAIN_MENU)\"",
        timeout=90,
    )
    print("IMPORT CHECK:\n" + out)
    if err:
        print(err)
    if "import_ok" not in out:
        print("ABORT: import failed")
        client.close()
        return 1

    out, err, code = run(
        client,
        "systemctl restart qooq-api qooq-admin qooq-bot && sleep 3 && "
        "systemctl is-active qooq-api qooq-admin qooq-bot",
        timeout=90,
    )
    print("RESTART:\n" + out)
    if err:
        print(err)

    services = [line.strip() for line in out.strip().splitlines() if line.strip()]
    # is-active prints one status per line; last 3 should be active
    statuses = services[-3:] if len(services) >= 3 else services
    print("STATUSES:", statuses)

    out, err, _ = run(
        client,
        "journalctl -u qooq-bot -u qooq-api -u qooq-admin --since '1 min ago' --no-pager | tail -n 40",
        timeout=30,
    )
    print("LOGS:\n" + out)

    client.close()
    if statuses != ["active", "active", "active"]:
        print("WARNING: not all services active")
        return 1
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
