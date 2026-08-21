"""Safely add Yandex lte-xhttp inbound on :8443 + register Happ profile.

Does NOT modify the production VLESS TCP :443 inbound settings —
only copies its client list into the new inbound.
Rollback on xray -test / restart failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
TOKEN = "RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc"

FILES = [
    "src/services/vpn_config.py",
    "src/services/xray_sync.py",
    "src/services/vpn_servers_sync.py",
]

XHTTP_INBOUND = {
    "tag": "lte-xhttp",
    "listen": "0.0.0.0",
    "port": 8443,
    "protocol": "vless",
    "settings": {"clients": [], "decryption": "none"},
    "streamSettings": {
        "network": "xhttp",
        "security": "tls",
        "tlsSettings": {
            "alpn": ["h2", "http/1.1"],
            "certificates": [
                {
                    "certificateFile": "/etc/xray/certs/fullchain.cer",
                    "keyFile": "/etc/xray/certs/white2.qooqvpn.ru.key",
                }
            ],
        },
        "xhttpSettings": {
            "path": "/static/getFile/video/segment.ts",
            "host": "white2.qooqvpn.ru",
            "mode": "packet-up",
            "extra": {
                "noSSEHeader": True,
                "scMaxBufferedPosts": 30,
                "uplinkHTTPMethod": "GET",
            },
        },
    },
}


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[str, str, int]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


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

    # --- Step 1: carefully patch Yandex config ---
    print("=== Patch Yandex xray (backup + test + rollback) ===")
    out, err, code = run(
        client,
        r'''
set -e
ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 'bash -s' <<'EOS'
set -euo pipefail
CFG=/usr/local/etc/xray/config.json
BK=/usr/local/etc/xray/config.json.bak.lte_xhttp_$(date +%Y%m%d_%H%M%S)
sudo cp -a "$CFG" "$BK"
echo BACKUP=$BK
python3 - <<'PY'
import json, copy
from pathlib import Path
cfg_path = Path("/tmp/xray_work.json")
# read via stdin file prepared below
PY
sudo cat "$CFG" > /tmp/xray_work.json
python3 - <<'PY'
import json, copy
from pathlib import Path
cfg = json.loads(Path("/tmp/xray_work.json").read_text())
# find tcp 443
tcp = None
for ib in cfg.get("inbounds", []):
    if ib.get("protocol")=="vless" and ib.get("port")==443:
        tcp = ib
        break
if not tcp:
    raise SystemExit("NO_TCP_443")
# already have lte-xhttp?
for ib in cfg.get("inbounds", []):
    if ib.get("tag")=="lte-xhttp" or ib.get("port")==8443:
        print("ALREADY_PRESENT")
        Path("/tmp/xray_work.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
        raise SystemExit(0)
inbound = {
  "tag": "lte-xhttp",
  "listen": "0.0.0.0",
  "port": 8443,
  "protocol": "vless",
  "settings": {
    "clients": copy.deepcopy(tcp.get("settings", {}).get("clients", [])),
    "decryption": "none",
  },
  "streamSettings": {
    "network": "xhttp",
    "security": "tls",
    "tlsSettings": {
      "alpn": ["h2", "http/1.1"],
      "certificates": copy.deepcopy(
        (tcp.get("streamSettings") or {}).get("tlsSettings", {}).get("certificates", [])
      ),
    },
    "xhttpSettings": {
      "path": "/static/getFile/video/segment.ts",
      "host": "white2.qooqvpn.ru",
      "mode": "packet-up",
      "extra": {
        "noSSEHeader": True,
        "scMaxBufferedPosts": 30,
        "uplinkHTTPMethod": "GET",
      },
    },
  },
}
# insert after first inbound
cfg["inbounds"].insert(1, inbound)
Path("/tmp/xray_work.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
print("PATCHED clients", len(inbound["settings"]["clients"]))
PY
sudo cp /tmp/xray_work.json /tmp/xray_candidate.json
# validate
if sudo xray run -test -c /tmp/xray_candidate.json; then
  echo TEST_OK
else
  echo TEST_FAIL
  sudo cp -a "$BK" "$CFG"
  exit 1
fi
sudo cp /tmp/xray_candidate.json "$CFG"
sudo chmod 644 "$CFG"
if sudo systemctl restart xray; then
  sleep 1
  if systemctl is-active --quiet xray && ss -lntp | grep -q ':8443'; then
    echo RESTART_OK
    ss -lntp | grep -E ':443|:8443' || true
  else
    echo RESTART_BAD_ROLLBACK
    sudo cp -a "$BK" "$CFG"
    sudo systemctl restart xray
    exit 1
  fi
else
  echo RESTART_FAIL_ROLLBACK
  sudo cp -a "$BK" "$CFG"
  sudo systemctl restart xray
  exit 1
fi
# verify 443 still up
ss -lntp | grep ':443' || { echo PORT443_DOWN; exit 1; }
echo DONE_YANDEX
EOS
''',
        timeout=90,
    )
    print(out)
    if err.strip():
        print(err[-2000:])
    if code != 0 or "DONE_YANDEX" not in out:
        print("Yandex patch failed, aborting DB changes")
        client.close()
        return 1

    # --- Step 2: register config + sync ---
    print("=== Register Happ profile + sync ===")
    out, err, code = run(
        client,
        f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.config import get_settings
from src.core.enums import VpnConfigType
from src.models import VpnConfig, VpnServer, Subscription
from src.services.vpn_config import (
    VPN_HOST, LTE_XHTTP_CONFIG_NAME, export_lte_xhttp_json_template,
    build_credential_share_link,
)
from src.services.vpn_config_store import VpnConfigStore
from src.services.config_credentials import ConfigCredentialService
from src.services import SubscriptionService
from src.api.routes.sub_feed import _credential_remark

TOKEN = "{TOKEN}"

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        entry = (await session.execute(
            select(VpnServer).where(VpnServer.host == VPN_HOST, VpnServer.is_active.is_(True)).limit(1)
        )).scalar_one_or_none()
        if not entry:
            raise SystemExit("no yandex server row")
        store = VpnConfigStore(session)
        existing = (await session.execute(
            select(VpnConfig).where(VpnConfig.name.in_([LTE_XHTTP_CONFIG_NAME, "LTE", "🇷🇺 LTE Обход"]))
        )).scalars().all()
        cfg = next((c for c in existing if c.name == LTE_XHTTP_CONFIG_NAME), None) or (existing[0] if existing else None)
        template = export_lte_xhttp_json_template()
        if cfg:
            cfg.name = LTE_XHTTP_CONFIG_NAME
            cfg.config_template = template
            cfg.config_type = VpnConfigType.XRAY_JSON
            cfg.is_active = True
            cfg.is_default = False
            cfg.server_id = entry.id
            print("updated config", cfg.id)
        else:
            cfg = await store.create_config(
                server_id=entry.id,
                name=LTE_XHTTP_CONFIG_NAME,
                config_type=VpnConfigType.XRAY_JSON,
                config_template=template,
                is_default=False,
            )
            print("created config", cfg.id)

        sub = (await session.execute(
            select(Subscription).where(Subscription.subscription_token == TOKEN)
        )).scalar_one_or_none()
        if not sub:
            raise SystemExit("token sub not found")
        creds, changed = await ConfigCredentialService(session, settings).ensure_credentials(sub)
        print("ensure_credentials changed", changed, "count", len(creds))
        ok = await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print("sync_ok", ok)

        active = await ConfigCredentialService(session, settings).list_active(sub.id)
        lte = None
        for c in active:
            if c.vpn_config and c.vpn_config.name == LTE_XHTTP_CONFIG_NAME:
                lte = c
                break
        if not lte:
            print("LTE cred missing")
            return
        link = build_credential_share_link(
            lte.client_uuid,
            lte.vpn_config.config_type.value,
            lte.vpn_config.config_template,
            _credential_remark(lte),
        )
        print("LTE_VLESS=" + link)
        print("SUB_URL=https://keys.qooqvpn.ru/sub/" + TOKEN)
        print("ACTIVE_NAMES=")
        for c in active:
            if c.vpn_config:
                print(" -", c.vpn_config.name)

asyncio.run(main())
PY
""",
        timeout=180,
    )
    print(out)
    if err.strip():
        print(err[-3000:])

    # restart api to pick code
    run(client, "systemctl restart qooq-api qooq-admin")
    time.sleep(3)
    out, _, _ = run(client, "systemctl is-active qooq-api qooq-admin; ss -lntp | grep 8000 || true")
    print(out)

    # probe sub
    out, _, _ = run(
        client,
        f'''
sleep 2
curl -sS -o /tmp/sub_out.txt -w "HTTP %{{http_code}}\\n" "http://127.0.0.1:8000/sub/{TOKEN}"
python3 - <<'PY'
import base64, urllib.parse
raw=open("/tmp/sub_out.txt","rb").read().strip()
body=base64.b64decode(raw).decode()
for l in body.splitlines():
  if not l.strip():
    continue
  name=urllib.parse.unquote(l.rsplit("#",1)[-1])
  print("-", l.split("://")[0], name)
  if "LTE" in name and "Россия" not in name:
    print("TEST_LINK_LINE="+l)
PY
''',
    )
    print(out)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
