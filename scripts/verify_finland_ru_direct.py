"""Verify Finland RU-direct in subscription feed."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.parse

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
TOKEN = "RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    def run(cmd: str, t: int = 60) -> str:
        _, o, e = client.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    for _ in range(20):
        out = run("curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true")
        if "200" in out:
            break
        time.sleep(1)

    out = run(
        f"curl -sS -D - -o /tmp/sub_body.b64 http://127.0.0.1:8000/sub/{TOKEN} | "
        "head -n 40; echo '---'; "
        "python3 - <<'PY'\n"
        "import base64,json,urllib.parse\n"
        "raw=open('/tmp/sub_body.b64','rb').read().strip()\n"
        "body=base64.b64decode(raw).decode()\n"
        "for line in body.splitlines():\n"
        "  if line.startswith('happ://routing/'):\n"
        "    print('ROUTING', line[:70]+'...')\n"
        "    continue\n"
        "  if line.startswith(('vless://','hysteria','hy2://')):\n"
        "    name=urllib.parse.unquote(line.rsplit('#',1)[-1])\n"
        "    if 'Финляндия' in name or 'Finland' in name:\n"
        "      print('FIN_AS_VLESS', name)\n"
        "    continue\n"
        "  try:\n"
        "    data=json.loads(base64.b64decode(line).decode())\n"
        "  except Exception:\n"
        "    continue\n"
        "  if 'outbounds' not in data: continue\n"
        "  rules=str(data.get('routing',{}).get('rules'))\n"
        "  print('JSON', data.get('remarks'), 'ozon=', 'ozon' in rules, 'wb=', 'wildberries' in rules or 'wb.ru' in rules)\n"
        "print('total_lines', len([l for l in body.splitlines() if l.strip()]))\n"
        "PY"
    )
    print(out)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
