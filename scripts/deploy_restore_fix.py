"""Deploy restore/credentials fix and repair subscription 5."""

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
    "src/services/config_credentials.py",
    "src/services/device_limit.py",
    "src/bot/handlers/devices.py",
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


def run(client, cmd, timeout=120):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30, banner_timeout=30)

    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), remote)
    sftp.close()

    out, err, _ = run(
        client,
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.services.config_credentials import ConfigCredentialService; "
        "from src.services.device_limit import DeviceLimitService; print('import_ok')\"",
    )
    print(out)
    if err:
        print(err)
    if "import_ok" not in out:
        print("ABORT")
        client.close()
        return 1

    repair = r'''
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.models import Subscription
from src.services import SubscriptionService
from src.services.config_credentials import ConfigCredentialService

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.config), selectinload(Subscription.devices))
            .where(Subscription.id == 5)
        )
        sub = result.scalar_one()
        creds = await ConfigCredentialService(session, settings).refresh_subscription(sub)
        print("refreshed_creds", len(creds), [str(c.client_uuid) for c in creds])
        await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print("sync_ok")

asyncio.run(main())
PY
'''
    out, err, code = run(client, repair, timeout=180)
    print("REPAIR:\n", out)
    if err:
        print(err)
    if code != 0 or "sync_ok" not in out:
        print("WARN: repair may have failed")

    out, err, _ = run(
        client,
        "systemctl restart qooq-api qooq-bot && sleep 3 && "
        "systemctl is-active qooq-api qooq-bot && "
        "curl -s 'https://keys.qooqvpn.ru/sub/_-o9EsNoNLjwdJ5RdLuvGU5OR9dde18GCFrggpD9PAo' | "
        "python3 -c \"import sys,base64; d=base64.b64decode(sys.stdin.read().strip()); print(d.decode())\"",
        timeout=90,
    )
    print(out)
    if err:
        print(err)

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
