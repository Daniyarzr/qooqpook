"""Redeploy multi-server feed (entry-only hosts) and verify."""

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


def run(client, cmd, timeout=120):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return out, err, stdout.channel.recv_exit_status()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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
        "systemctl restart qooq-api && sleep 3 && systemctl is-active qooq-api",
    )
    print(out, err)

    out, err, _ = run(
        client,
        r"""
cd /opt/qooq-vpn && .venv/bin/python <<'PY'
import asyncio
from sqlalchemy import text
from src.db.session import async_session_factory

async def main():
    async with async_session_factory() as s:
        r = await s.execute(text("select id, subscription_token, status from subscriptions where id=5"))
        row = dict(r.mappings().first())
        print('SUB', row)
        token = row['subscription_token']
        r = await s.execute(text('''
            select c.id, v.id as cfg, s.name as server_name, c.client_uuid::text
            from subscription_config_credentials c
            join vpn_configs v on v.id=c.vpn_config_id
            join vpn_servers s on s.id=v.server_id
            where c.subscription_id=5 and c.revoked_at is null order by c.id
        '''))
        creds = [dict(x) for x in r.mappings()]
        print('CREDS', len(creds), creds)
        print('TOKEN', token)

asyncio.run(main())
PY
""",
    )
    print(out)
    if err:
        print(err)

    # Extract token and curl feed
    out2, err2, _ = run(
        client,
        r"""
TOKEN=$(cd /opt/qooq-vpn && .venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import text
from src.db.session import async_session_factory
async def main():
    async with async_session_factory() as s:
        r=await s.execute(text("select subscription_token from subscriptions where id=5"))
        print(r.scalar_one())
asyncio.run(main())
PY
)
echo TOKEN=$TOKEN
curl -s -o /tmp/sub_b.txt -w "HTTP %{http_code}\n" "https://keys.qooqvpn.ru/sub/$TOKEN"
python3 - <<'PY'
import base64
raw=open('/tmp/sub_b.txt','rb').read().strip()
pad=b'='*((4-len(raw)%4)%4)
text=base64.b64decode(raw+pad).decode('utf-8','replace')
print(text)
print('LINES', len([l for l in text.splitlines() if l.strip()]))
PY
""",
    )
    print(out2)
    if err2:
        print(err2)

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
