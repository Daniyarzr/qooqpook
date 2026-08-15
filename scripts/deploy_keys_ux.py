"""Deploy keys page UX fix."""
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
        "\"from fastapi import BackgroundTasks; from src.admin.app import create_admin_app; "
        "create_admin_app(); print('ok')\""
    )
    print("IMPORT:", out.strip(), err.strip(), "code", code)
    if "ok" not in out:
        client.close()
        return 1

    out, err, _ = run("systemctl restart qooq-admin && sleep 2 && systemctl is-active qooq-admin")
    print("RESTART:", out.strip())

    cleanup = r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from src.db.session import async_session_factory
from src.admin.services import AdminService

async def main():
    async with async_session_factory() as s:
        svc = AdminService(s)
        n = await svc.purge_revoked_manual_keys()
        keys = await svc.list_manual_keys(active_only=True)
        await s.commit()
        print('purged', n)
        print('active', [(k.id, k.label) for k in keys])

asyncio.run(main())
PY
"""
    out, err, code = run(cleanup)
    print("DB:", out)
    if err:
        print(err)
    client.close()
    print("DONE")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
