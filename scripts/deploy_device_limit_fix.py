"""Deploy device-limit fix: no IP/UA phantoms, purge, auto-restore."""

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
    "src/services/device_limit.py",
    "src/services/__init__.py",
    "src/bot/handlers/devices.py",
    "src/bot/handlers/profile.py",
    "src/bot/handlers/subscription.py",
    "src/bot/keyboards/inline.py",
    "src/bot/texts/messages.py",
    "src/api/routes/sub_feed.py",
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
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.services.device_limit import is_phantom_hwid, DeviceLimitService; "
        "assert is_phantom_hwid('b6e9b020c46074419cb290840b640519', 'Mozilla/5.0'); "
        "assert not is_phantom_hwid('zy2hg4je5jx0h55s', 'Happ/4.8.3/ios/x'); "
        "print('import_ok')\"",
        timeout=60,
    )
    print("IMPORT:\n" + out)
    if err:
        print(err)
    if "import_ok" not in out:
        print("ABORT: import failed")
        client.close()
        return 1

    out, err, code = run(
        client,
        "systemctl restart qooq-api qooq-bot && sleep 3 && "
        "systemctl is-active qooq-api qooq-bot qooq-admin",
        timeout=90,
    )
    print("RESTART:\n" + out)
    if err:
        print(err)

    cleanup = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.models import Subscription
from src.services.device_limit import DeviceLimitService
from sqlalchemy import select

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        svc = DeviceLimitService(session, settings)
        removed = await svc.purge_phantom_hwids()
        print('purged_phantoms', removed)

        result = await session.execute(
            select(Subscription).where(Subscription.suspension_reason == 'device_limit')
        )
        restored = 0
        for sub in result.scalars().all():
            ok = await svc.try_reactivate(sub, clear_hwids=False)
            print('sub', sub.id, 'hwids', await svc.count_hwids(sub.id), 'restored', ok)
            if ok:
                restored += 1
        await session.commit()
        print('restored_count', restored)

asyncio.run(main())
PY
"""
    out, err, code = run(client, cleanup, timeout=120)
    print("CLEANUP:\n" + out)
    if err:
        print("CLEANUP STDERR:\n" + err)
    if code != 0:
        print("WARNING: cleanup exit", code)

    out, err, _ = run(
        client,
        "journalctl -u qooq-api -u qooq-bot --since '1 min ago' --no-pager | tail -n 30",
        timeout=30,
    )
    print("LOGS:\n" + out)

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
