import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/services/__init__.py",
    "src/services/vpn_config.py",
    "src/api/routes/sub_feed.py",
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


def run(cmd: str, timeout: int = 90) -> str:
    print("====", cmd[:100])
    ch = t.open_session()
    ch.settimeout(timeout)
    ch.exec_command(cmd)
    started = time.time()
    while not ch.exit_status_ready():
        if time.time() - started > timeout:
            print("TIMEOUT")
            return ""
        time.sleep(0.2)
    out = b""
    while ch.recv_ready():
        out += ch.recv(65536)
    err = b""
    while ch.recv_stderr_ready():
        err += ch.recv_stderr(16384)
    text = out.decode("utf-8", errors="replace")
    if err:
        text += "\n" + err.decode("utf-8", errors="replace")[-1500:]
    print(text)
    return text


run("systemctl restart qooq-api")
time.sleep(4)
run("systemctl is-active qooq-api")
run(
    r"""
cd /opt/qooq-vpn && PYTHONPATH=/opt/qooq-vpn .venv/bin/python - <<'PY'
import asyncio, time, urllib.request
from sqlalchemy import text
from src.db.session import async_session_factory

async def main():
    async with async_session_factory() as s:
        token = (await s.execute(text(
            "SELECT subscription_token FROM subscriptions WHERE user_id=28 ORDER BY id DESC LIMIT 1"
        ))).scalar_one()
    url = f"http://127.0.0.1:8000/sub/{token}?format=link"
    t0 = time.time()
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        headers = dict(resp.headers)
    dt = time.time() - t0
    print("elapsed_sec", round(dt, 3))
    print("status_headers", {k: headers.get(k) for k in [
        "profile-title", "sub-expire", "routing", "subscription-always-hwid-enable"
    ]})
    lines = [l for l in body.strip().splitlines() if l.strip()]
    print("lines", len(lines))
    from urllib.parse import unquote
    for line in lines:
        if line.startswith("happ://"):
            print("ROUTING ok")
        elif "#" in line:
            print(unquote(line.split("#",1)[1]))
asyncio.run(main())
PY
"""
)
client.close()
print("DONE")
