"""Deploy connect-guide bot button + admin settings editor."""

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
    "src/services/system_settings.py",
    "src/bot/keyboards/inline.py",
    "src/bot/handlers/profile.py",
    "src/admin/services.py",
    "src/admin/app.py",
    "src/admin/templates/settings.html",
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
    sftp.close()

    def run(cmd: str, t: int = 60) -> int:
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        text = (out + (("\n" + err) if err.strip() else "")).strip()
        if text:
            print(text)
        return code

    print("=== import check ===")
    code = run(
        f"cd {REMOTE} && .venv/bin/python -c "
        "'from src.services.system_settings import CONNECT_GUIDE_KEY; "
        "from src.bot.handlers import profile; "
        "print(CONNECT_GUIDE_KEY)'"
    )
    if code != 0:
        client.close()
        return code

    print("=== restart ===")
    run("systemctl restart qooq-bot qooq-admin")
    time.sleep(4)
    run("systemctl is-active qooq-bot qooq-admin qooq-api")
    run("journalctl -u qooq-bot -n 10 --no-pager")
    run("journalctl -u qooq-admin -n 10 --no-pager")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
