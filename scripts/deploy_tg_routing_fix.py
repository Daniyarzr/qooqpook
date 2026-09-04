import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = ["src/services/vpn_config.py"]

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
systemctl restart qooq-api
for i in $(seq 1 40); do
  if ss -lntp 2>/dev/null | grep -q ':8000'; then echo LISTEN_$i; break; fi
  sleep 2
done
systemctl is-active qooq-api
cd /opt/qooq-vpn
TOKEN=$(PYTHONPATH=/opt/qooq-vpn .venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import text
from src.db.session import async_session_factory
async def main():
  async with async_session_factory() as s:
    print((await s.execute(text("SELECT subscription_token FROM subscriptions WHERE user_id=28 ORDER BY id DESC LIMIT 1"))).scalar_one())
asyncio.run(main())
PY
)
curl -sS "http://127.0.0.1:8000/sub/${TOKEN}?format=link" -o /tmp/b2.txt
python3 - <<'PY'
import base64,json
from urllib.parse import unquote
body=open('/tmp/b2.txt',encoding='utf-8').read().splitlines()
for line in body:
  if line.startswith('happ://routing/'):
    data=json.loads(base64.b64decode(line.split('/')[-1]+'===').decode())
    print('GlobalProxy', data.get('GlobalProxy'))
    print('ProxyIp', data.get('ProxyIp'))
    print('RouteOrder', data.get('RouteOrder'))
    print('ProxySites_n', len(data.get('ProxySites') or []))
  elif '#' in line:
    print('name', unquote(line.split('#',1)[1]))
PY
'''
sftp = client.open_sftp()
with sftp.file('/tmp/deploy_tg_fix.sh','w') as f:
    f.write(script)
sftp.chmod('/tmp/deploy_tg_fix.sh', 0o755)
sftp.close()

ch = t.open_session()
ch.settimeout(180)
ch.exec_command('bash /tmp/deploy_tg_fix.sh')
started = time.time()
while not ch.exit_status_ready():
    if time.time() - started > 180:
        print('TIMEOUT')
        break
    time.sleep(0.4)
out = b''
while ch.recv_ready():
    out += ch.recv(65536)
print(out.decode('utf-8','replace'))
client.close()
print('DONE')
