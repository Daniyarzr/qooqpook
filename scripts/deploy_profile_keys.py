"""Deploy profile UI, remove add-device, broadcast menu btn, manual keys."""

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
    "alembic/versions/014_manual_vpn_keys.py",
    "alembic/env.py",
    "src/models/__init__.py",
    "src/services/__init__.py",
    "src/services/xray_sync.py",
    "src/bot/handlers/profile.py",
    "src/bot/handlers/devices.py",
    "src/bot/handlers/broadcast.py",
    "src/bot/handlers/start.py",
    "src/bot/keyboards/inline.py",
    "src/bot/texts/messages.py",
    "src/admin/app.py",
    "src/admin/services.py",
    "src/admin/templates/base.html",
    "src/admin/templates/keys.html",
    "src/api/routes/miniapp.py",
    "src/api/static/miniapp/app.js",
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
        "\"from src.models import ManualVpnKey; "
        "from src.bot.keyboards.inline import broadcast_menu_keyboard, devices_keyboard; "
        "from src.admin.app import create_admin_app; "
        "from src.services.xray_sync import XrayClient; "
        "kb = broadcast_menu_keyboard(); "
        "print('import_ok', ManualVpnKey.__tablename__, "
        "XrayClient(user_id=0, credential_id=1, client_uuid=__import__('uuid').uuid4(), "
        "email_override='qooq-manual-1').email)\"",
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
    statuses = services[-3:] if len(services) >= 3 else services
    print("STATUSES:", statuses)

    out, err, _ = run(
        client,
        "journalctl -u qooq-bot -u qooq-api -u qooq-admin --since '1 min ago' --no-pager | tail -n 50",
        timeout=30,
    )
    print("LOGS:\n" + out)

    out, err, _ = run(
        client,
        "curl -s -o /dev/null -w '%{http_code}' -L http://127.0.0.1:8001/keys; echo; "
        "cd /opt/qooq-vpn && .venv/bin/python - <<'PY'\n"
        "import asyncio\n"
        "from sqlalchemy import text\n"
        "from src.db.session import async_session_factory\n"
        "async def main():\n"
        "    async with async_session_factory() as s:\n"
        "        r = await s.execute(text(\"SELECT to_regclass('public.manual_vpn_keys')\"))\n"
        "        print('table', r.scalar())\n"
        "asyncio.run(main())\n"
        "PY",
        timeout=60,
    )
    print("VERIFY:\n" + out)
    if err:
        print(err)

    client.close()
    if statuses != ["active", "active", "active"]:
        print("WARNING: not all services active")
        return 1
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
