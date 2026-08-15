"""Deploy multi-server subscription feed and refresh credentials."""

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
    "src/services/vpn_config.py",
    "src/services/__init__.py",
    "src/api/routes/sub_feed.py",
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


def run(client, cmd, timeout=180):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting...")
    client.connect(HOST, username="root", password=PASSWORD, timeout=45, banner_timeout=45)

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
        "\"from src.services.config_credentials import ConfigCredentialService; print('import_ok')\"",
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
from src.core.enums import SubscriptionStatus
from src.core.utils import utcnow
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
            .where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                Subscription.expires_at > utcnow(),
            )
        )
        subs = list(result.scalars().unique().all())
        cred_service = ConfigCredentialService(session, settings)
        for sub in subs:
            creds = await cred_service.ensure_credentials(sub)
            print(f"sub={sub.id} creds={len(creds)}")
        await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print("sync_ok")

asyncio.run(main())
PY
'''
    out, err, code = run(client, repair, timeout=180)
    print("REPAIR:\n", out)
    if err:
        print("REPAIR ERR:\n", err)

    out, err, _ = run(
        client,
        "systemctl restart qooq-api qooq-bot && sleep 4 && systemctl is-active qooq-api qooq-bot",
        timeout=90,
    )
    print("RESTART:\n", out)

    out, err, _ = run(
        client,
        "sleep 2; curl -s 'https://keys.qooqvpn.ru/sub/_-o9EsNoNLjwdJ5RdLuvGU5OR9dde18GCFrggpD9PAo' > /tmp/sub_b.txt; "
        "python3 - <<'PY'\n"
        "import base64\n"
        "raw=open('/tmp/sub_b.txt','rb').read().strip()\n"
        "pad=b'='*((4-len(raw)%4)%4)\n"
        "text=base64.b64decode(raw+pad).decode('utf-8','replace')\n"
        "print(text)\n"
        "print('LINES', len([l for l in text.splitlines() if l.strip()]))\n"
        "PY",
        timeout=60,
    )
    print("FEED:\n", out)
    if err:
        print(err)

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
