"""Surgical deploy: only bot reply-keyboard / menu changes. Restarts qooq-bot only."""

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
    "src/bot/app.py",
    "src/bot/commands.py",
    "src/bot/handlers/start.py",
    "src/bot/handlers/reply_menu.py",
    "src/bot/keyboards/__init__.py",
    "src/bot/keyboards/reply.py",
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


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[str, str, int]:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
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

    out, err, code = run(client, "systemctl is-active qooq-bot qooq-api qooq-admin")
    print("PREFLIGHT services:\n" + out)
    if err:
        print(err)

    sftp = client.open_sftp()
    for rel in FILES:
        local = PROJECT / rel
        remote = f"{REMOTE_ROOT}/{rel}"
        ensure_remote_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print(f"Upload {rel}")
        sftp.put(str(local), remote)
    sftp.close()

    check_cmd = (
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.bot.commands import setup_bot_commands; "
        "from src.bot.keyboards.reply import main_reply_keyboard, BTN_BUY; "
        "from src.bot.handlers import reply_menu, start; "
        "from src.bot.app import create_bot; "
        "print('import_ok', BTN_BUY)\""
    )
    out, err, code = run(client, check_cmd, timeout=90)
    print("IMPORT CHECK:\n" + out)
    if err:
        print("STDERR:\n" + err)
    if "import_ok" not in out:
        print("ABORT: import failed, bot not restarted")
        client.close()
        return 1

    out, err, code = run(
        client,
        "systemctl restart qooq-bot && sleep 2 && "
        "systemctl is-active qooq-bot && "
        "systemctl status qooq-bot --no-pager -l | head -n 30",
        timeout=90,
    )
    print("RESTART:\n" + out)
    if err:
        print(err)

    services_out, err, _ = run(client, "systemctl is-active qooq-api qooq-admin qooq-bot")
    print("SERVICES AFTER:\n" + services_out)

    logs_out, err, _ = run(
        client,
        "journalctl -u qooq-bot -n 20 --no-pager",
        timeout=30,
    )
    print("BOT LOGS:\n" + logs_out)

    client.close()
    lines = [line.strip() for line in services_out.strip().splitlines()]
    if lines != ["active", "active", "active"]:
        print("WARNING: not all services active:", lines)
        return 1
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
