import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/repositories/__init__.py",
    "src/services/__init__.py",
    "src/bot/keyboards/inline.py",
    "src/bot/texts/messages.py",
    "src/bot/handlers/subscription.py",
]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    "148.135.184.188",
    username="root",
    password=PASSWORD,
    timeout=25,
    banner_timeout=25,
)
t = client.get_transport()
t.set_keepalive(5)
sftp = client.open_sftp()
for rel in FILES:
    sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    print("uploaded", rel)
sftp.close()

script = r'''#!/bin/bash
set +e
systemctl restart qooq-api qooq-bot
sleep 2
# wait api listen without killing ssh
for i in $(seq 1 45); do
  if ss -lntp 2>/dev/null | grep -q ':8000'; then echo API_OK_$i; break; fi
  sleep 2
done
systemctl is-active qooq-api qooq-bot
# verify renewable logic for user 28
cd /opt/qooq-vpn && PYTHONPATH=/opt/qooq-vpn .venv/bin/python - <<'PY'
import asyncio
from src.db.session import async_session_factory
from src.repositories import SubscriptionRepository

async def main():
    async with async_session_factory() as s:
        repo = SubscriptionRepository(s)
        r = await repo.get_renewable_by_user(28)
        print("renewable28", None if not r else (r.id, str(r.status), r.subscription_token[:12], str(r.expires_at)))
        m = await repo.get_manageable_by_user(28)
        print("manageable28", None if not m else (m.id, str(m.status)))
asyncio.run(main())
PY
journalctl -u qooq-bot --since "30 sec ago" --no-pager | tail -n 8
'''

sftp = client.open_sftp()
with sftp.file("/tmp/deploy_renew.sh", "w") as f:
    f.write(script)
sftp.chmod("/tmp/deploy_renew.sh", 0o755)
sftp.close()

ch = t.open_session()
ch.settimeout(200)
ch.exec_command("bash /tmp/deploy_renew.sh")
started = time.time()
while not ch.exit_status_ready():
    if time.time() - started > 200:
        print("TIMEOUT")
        break
    time.sleep(0.4)
out = b""
while ch.recv_ready():
    out += ch.recv(65536)
err = b""
while ch.recv_stderr_ready():
    err += ch.recv_stderr(16384)
print(out.decode("utf-8", errors="replace"))
if err.strip():
    print(err.decode("utf-8", errors="replace")[-1500:])
client.close()
print("DONE")
