"""Deploy keys create crash fix + cleanup duplicate keys."""
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
    "src/admin/app.py",
    "src/admin/services.py",
    "src/admin/templates/keys.html",
    "src/services/__init__.py",
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
        "\"from src.admin.app import create_admin_app; create_admin_app(); print('ok')\"",
        timeout=60,
    )
    print("IMPORT:", out, err)
    if "ok" not in out:
        print("ABORT")
        client.close()
        return 1

    out, err, _ = run(
        "systemctl restart qooq-admin qooq-api && sleep 3 && systemctl is-active qooq-admin qooq-api",
        timeout=60,
    )
    print("RESTART:", out)

    cleanup = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from sqlalchemy import text
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.admin.services import AdminService

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        # leave newest key, revoke older duplicates with same label
        r = await session.execute(text(
            "select id from manual_vpn_keys where revoked_at is null and label = :l order by id desc"
        ), {"l": "кучкуду три колодца"})
        ids = [row[0] for row in r]
        print('active_dupes', ids)
        svc = AdminService(session)
        for kid in ids[1:]:
            ok = await svc.revoke_manual_key(kid, settings=settings)
            print('revoked', kid, ok)
        await session.commit()
        r = await session.execute(text(
            "select id, label, revoked_at is not null as revoked from manual_vpn_keys order by id"
        ))
        for row in r:
            print(dict(row._mapping))

asyncio.run(main())
PY
"""
    out, err, code = run(cleanup, timeout=120)
    print("CLEANUP:", out)
    if err:
        print(err)
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
