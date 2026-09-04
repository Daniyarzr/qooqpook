"""Deploy Finland QooQ RU direct (WB/Ozon bypass) + Happ routing."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/services/vpn_config.py",
    "src/api/routes/sub_feed.py",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
        print("uploaded", rel)
    sftp.close()

    def run(cmd: str, t: int = 120) -> str:
        _, o, e = client.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    print(
        run(
            f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio, json
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import VpnConfig
from src.services.vpn_config import (
    FINLAND_CONFIG_NAME,
    FINLAND_NAME_ALIASES,
    export_finland_direct_json_template,
    build_happ_ru_direct_routing_link,
)

tpl = export_finland_direct_json_template()
assert "ozon.ru" in tpl and "wildberries.ru" in tpl
assert "geoip:ru" in tpl
link = build_happ_ru_direct_routing_link()
assert link.startswith("happ://routing/onadd/")

async def main():
    async with async_session_factory() as s:
        rows = (await s.execute(select(VpnConfig))).scalars().all()
        updated = 0
        for cfg in rows:
            if cfg.name in FINLAND_NAME_ALIASES or cfg.name == FINLAND_CONFIG_NAME:
                cfg.config_template = tpl
                cfg.is_active = True
                updated += 1
                print("updated config", cfg.id, cfg.name)
        await s.commit()
        print("finland_updated", updated)
        print("routing_link_len", len(link))

asyncio.run(main())
PY
"""
        )
    )
    print(run("systemctl restart qooq-api"))
    time.sleep(5)
    print(
        run(
            r"""
TOKEN=RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc
curl -sS -D /tmp/sub_hdrs.txt -o /tmp/sub_body.b64 "http://127.0.0.1:8000/sub/$TOKEN"
echo '--- HEADERS ---'
grep -iE 'routing:|HTTP/' /tmp/sub_hdrs.txt || true
echo '--- BODY DECODE ---'
python3 - <<'PY'
import base64
body=base64.b64decode(open('/tmp/sub_body.b64','rb').read().strip()).decode('utf-8','replace')
for i,line in enumerate(body.splitlines()):
    if line.startswith('happ://routing/'):
        print('ROUTING_OK', line[:60]+'...')
    elif line.startswith('vless://') and 'Финляндия' in __import__('urllib.parse').unquote(line):
        print('FIN_VLESS', line[:80])
    elif not line.startswith('vless://') and not line.startswith('hysteria') and not line.startswith('hy2://') and not line.startswith('happ://'):
        # maybe finland json b64
        try:
            import json, base64 as b64
            raw=b64.b64decode(line).decode()
            data=json.loads(raw)
            if 'outbounds' in data:
                domains=str(data.get('routing',{}).get('rules'))
                rem=data.get('remarks','')
                print('JSON_ENTRY remarks=', rem[:40], 'ozon' in domains, 'wb' in domains.lower() or 'wildberries' in domains)
        except Exception:
            pass
print('lines', len(body.splitlines()))
PY
"""
        )
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
