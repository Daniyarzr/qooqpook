"""Set vpn_servers max_users on production based on panel VPS hardware (2GB/1CPU → 75 users)."""

import os
import stat
import sys

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")
MAX_USERS = 50

REMOTE_SCRIPT = f"""#!/bin/bash
set -e
cd /opt/qooq-vpn
.venv/bin/python << 'PY'
import asyncio
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import VpnServer

MAX_USERS = {MAX_USERS}

async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(VpnServer))
        servers = list(result.scalars().all())
        for s in servers:
            print(f"{{s.id}} {{s.name}} host={{s.host}} max_users {{s.max_users}} -> {{MAX_USERS}}")
            s.max_users = MAX_USERS
        await session.commit()
        print("OK")

asyncio.run(main())
PY
free -m | head -2
nproc
"""


def main() -> int:
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    path = "/tmp/set_capacity.py"
    with sftp.open(path, "w") as f:
        f.write(REMOTE_SCRIPT.replace("\r\n", "\n"))
    sftp.chmod(path, stat.S_IRWXU)
    sftp.close()
    _, stdout, stderr = client.exec_command(f"bash {path}", timeout=60)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print(err, file=sys.stderr)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
