"""Verify Reality profile in sub + on Yandex inbound."""
from __future__ import annotations

import base64
import os
import sys
import time
import urllib.parse

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
TOKEN = "RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc"
UUID = "f794d7c9-ac53-4ff3-9ade-4c610a34651f"

REMOTE_CHECK = r"""
python3 - <<'PY'
import json
c=json.load(open('/usr/local/etc/xray/config.json'))
ib=[i for i in c['inbounds'] if i.get('tag')=='vless-reality'][0]
ids=[x['id'] for x in ib['settings']['clients']]
print('reality_clients', len(ids))
print('has_uuid', 'f794d7c9-ac53-4ff3-9ade-4c610a34651f' in ids)
print('port', ib['port'])
print('sni', ib['streamSettings']['realitySettings']['serverNames'])
PY
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    def run(cmd, t=90):
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        return code, out, err

    for _ in range(15):
        _, out, _ = run("systemctl is-active qooq-api; curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true")
        if "active" in out and "200" in out:
            break
        time.sleep(1)

    sftp = client.open_sftp()
    with sftp.file("/tmp/reality_check.sh", "w") as f:
        f.write(REMOTE_CHECK)
    sftp.close()
    run("scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no /tmp/reality_check.sh adminka@51.250.32.123:/tmp/")
    _, yout, yerr = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'bash /tmp/reality_check.sh'"
    )
    print("YANDEX", yout.strip())
    if yerr.strip():
        print("YERR", yerr[-500:])

    _, out, err = run(f"curl -sS http://127.0.0.1:8000/sub/{TOKEN}")
    if not out.strip():
        print("SUB_EMPTY", err[-500:])
        client.close()
        return 1
    body = base64.b64decode(out.strip()).decode()
    found = False
    for line in body.splitlines():
        name = urllib.parse.unquote(line.rsplit("#", 1)[-1])
        if "Tinkoff" in name:
            found = True
            print("PROFILE", name)
            print("LINK", line)
            assert UUID in line and "reality" in line
    print("HAS_TINKOFF_IN_SUB", found)
    client.close()
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
