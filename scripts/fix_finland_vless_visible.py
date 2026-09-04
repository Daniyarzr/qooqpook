"""Fix Finland QooQ back to vless:// in subscription (Happ-visible)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    sftp.put(str(PROJECT / "src/services/vpn_config.py"), f"{REMOTE}/src/services/vpn_config.py")
    sftp.close()

    def run(cmd: str, t: int = 90) -> str:
        _, o, e = client.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    print(run("systemctl restart qooq-api"))
    for _ in range(20):
        if "200" in run("curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true"):
            break
        time.sleep(1)

    print(
        run(
            r"""
TOKEN=RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc
curl -sS "http://127.0.0.1:8000/sub/$TOKEN" | python3 - <<'PY'
import sys, base64, urllib.parse
body=base64.b64decode(sys.stdin.buffer.read().strip()).decode()
for line in body.splitlines():
    if line.startswith('happ://routing/'):
        print('ROUTING_OK')
        continue
    if not line.startswith('vless://'):
        continue
    name=urllib.parse.unquote(line.rsplit('#',1)[-1])
    if 'Финляндия' in name or 'QooQ' in name:
        host=line.split('@',1)[1].split('?',1)[0]
        print('SERVER', name, host)
PY
"""
        )
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
