"""Deploy subscription key fixes."""
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
    "src/services/vpn_config.py",
    "src/services/device_limit.py",
    "src/services/config_credentials.py",
    "src/api/routes/sub_feed.py",
    "src/bot/handlers/devices.py",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=45, banner_timeout=45)

    sftp = client.open_sftp()
    for rel in FILES:
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    sftp.close()

    def run(cmd: str, timeout: int = 180):
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code

    out, err, code = run(
        "cd /opt/qooq-vpn && .venv/bin/python - <<'PY'\n"
        "import uuid\n"
        "from src.services.vpn_config import build_vless_link\n"
        "link = build_vless_link(uuid.uuid4(), 'QooQ')\n"
        "assert '51.250.32.123' in link and 'sni=' in link\n"
        "from src.services.config_credentials import ConfigCredentialService\n"
        "import inspect\n"
        "sig = inspect.signature(ConfigCredentialService.ensure_credentials)\n"
        "print('ok', link.split('@')[1].split('?')[0])\n"
        "PY"
    )
    print("IMPORT:", out)
    if err:
        print(err)
    if "ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        "systemctl restart qooq-api qooq-bot && sleep 3 && systemctl is-active qooq-api qooq-bot"
    )
    print("RESTART:", out.strip())

    # Force full Xray sync so existing credentials are on nodes
    sync = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.services import SubscriptionService

async def main():
    settings = get_settings()
    print('xray_sync_enabled', settings.xray_sync_enabled)
    async with async_session_factory() as session:
        ok = await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print('sync_ok', ok)

asyncio.run(main())
PY
"""
    out, err, code = run(sync, timeout=180)
    print("SYNC:", out)
    if err:
        print("SYNC ERR:", err)

    # Probe a live subscription feed
    probe = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio, base64, time
from sqlalchemy import text
from src.db.session import async_session_factory
import httpx

async def main():
    async with async_session_factory() as s:
        r = await s.execute(text(
            "select subscription_token from subscriptions "
            "where status in ('active','trial') and expires_at > now() "
            "order by id desc limit 1"
        ))
        token = r.scalar()
        print('token', bool(token))
        if not token:
            return
    t0 = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f'http://127.0.0.1:8000/sub/{token}')
    dt = time.time() - t0
    print('status', resp.status_code, 'seconds', round(dt,2), 'bytes', len(resp.content))
    if resp.status_code == 200 and resp.content:
        try:
            body = base64.b64decode(resp.content).decode('utf-8', 'replace')
        except Exception:
            body = resp.text
        lines = [ln for ln in body.splitlines() if ln.strip()]
        print('links', len(lines))
        for ln in lines[:5]:
            print('LINK', ln[:120])

asyncio.run(main())
PY
"""
    out, err, code = run(probe, timeout=90)
    print("PROBE:", out)
    if err:
        print(err)

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
