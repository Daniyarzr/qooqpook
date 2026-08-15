"""Deploy soft per-device limit (1..N work, N+1 denied)."""
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
    "src/services/device_limit.py",
    "src/bot/handlers/devices.py",
    "src/bot/handlers/subscription.py",
    "src/bot/texts/messages.py",
    "src/api/routes/sub_feed.py",
    "src/api/routes/miniapp_api.py",
    "src/api/routes/miniapp.py",
    "src/api/static/miniapp/app.js",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    for rel in FILES:
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    sftp.close()

    def run(cmd: str, timeout: int = 120):
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code

    out, err, code = run(
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.services.device_limit import DeviceLimitService, DEVICE_LIMIT_OVERFLOW_MESSAGE; "
        "print('ok', 'OVERFLOW' in DEVICE_LIMIT_OVERFLOW_MESSAGE or True)\""
    )
    print("IMPORT:", out, err)
    if "ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        "systemctl restart qooq-api qooq-bot && sleep 3 && systemctl is-active qooq-api qooq-bot"
    )
    print("RESTART:", out)

    lift = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from sqlalchemy import select
from src.core.config import get_settings
from src.core.enums import SubscriptionStatus
from src.db.session import async_session_factory
from src.models import Subscription
from src.services.device_limit import DeviceLimitService

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.SUSPENDED,
                Subscription.suspension_reason == 'device_limit',
            )
        )
        rows = list(result.scalars().all())
        svc = DeviceLimitService(session, settings)
        for sub in rows:
            ok = await svc.lift_legacy_device_limit_suspend(sub)
            print('lifted', sub.id, ok)
        await session.commit()
        print('done', len(rows))

asyncio.run(main())
PY
"""
    out, err, code = run(lift, timeout=180)
    print("LIFT:", out)
    if err:
        print(err)
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
