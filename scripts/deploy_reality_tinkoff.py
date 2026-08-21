"""Add VLESS Reality inbound for Tinkoff Mobile — keep white2/xhttp intact.

SNI www.microsoft.com -> 127.0.0.1:11443 (Reality)
SNI white2.qooqvpn.ru  -> 127.0.0.1:10443 (TCP TLS production)
SNI white.qooqvpn.ru   -> 127.0.0.1:18443 (xHTTP)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
TOKEN = "RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc"
REALITY_SNI = "www.microsoft.com"
REALITY_CONFIG_NAME = "🇷🇺 Tinkoff"

STREAM = f"""stream {{
    map $ssl_preread_server_name $qooq_backend {{
        {REALITY_SNI}      127.0.0.1:11443;
        white.qooqvpn.ru   127.0.0.1:18443;
        white2.qooqvpn.ru  127.0.0.1:10443;
        default            127.0.0.1:10443;
    }}
    server {{
        listen 443 reuseport;
        listen [::]:443 reuseport;
        proxy_pass $qooq_backend;
        ssl_preread on;
        proxy_connect_timeout 5s;
        proxy_timeout 300s;
    }}
}}
"""

# Shell script: no nested triple-quotes — Python reads PRIV/SHORT from env.
SH = r"""
set -euxo pipefail
CFG=/usr/local/etc/xray/config.json
sudo cp -a "$CFG" /usr/local/etc/xray/config.json.bak.pre_reality

KEYS=$(xray x25519)
echo "$KEYS"
PRIV=$(echo "$KEYS" | awk '/Private/{print $NF}')
PUB=$(echo "$KEYS" | awk '/Password/{print $NF}')
if [ -z "$PUB" ]; then PUB=$(echo "$KEYS" | awk '/Public/{print $NF}'); fi
SHORT=$(openssl rand -hex 4)
echo PRIV=$PRIV
echo PUB=$PUB
echo SHORT=$SHORT
echo "$PUB" > /tmp/reality_pub.txt
echo "$SHORT" > /tmp/reality_short.txt

sudo rm -f /tmp/xray_work.json /tmp/xray_candidate.json
sudo cp "$CFG" /tmp/xray_work.json
sudo chown adminka:adminka /tmp/xray_work.json

export PRIV SHORT
python3 <<'PY'
import copy
import json
import os
from pathlib import Path

cfg = json.loads(Path("/tmp/xray_work.json").read_text())
priv = os.environ["PRIV"]
short = os.environ["SHORT"]
clients = []
for ib in cfg["inbounds"]:
    if ib.get("protocol") != "vless":
        continue
    tag = ib.get("tag")
    stream = ib.get("streamSettings") or {}
    network = stream.get("network") or "tcp"
    if tag in ("vless-tcp", "lte-xhttp") or network == "tcp":
        clients = copy.deepcopy(ib.get("settings", {}).get("clients", []))
        if clients:
            break
cfg["inbounds"] = [
    ib
    for ib in cfg["inbounds"]
    if ib.get("tag") != "vless-reality" and ib.get("port") != 11443
]
reality = {
    "tag": "vless-reality",
    "listen": "127.0.0.1",
    "port": 11443,
    "protocol": "vless",
    "settings": {"clients": clients, "decryption": "none"},
    "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "show": False,
            "dest": "www.microsoft.com:443",
            "xver": 0,
            "serverNames": ["www.microsoft.com"],
            "privateKey": priv,
            "shortIds": ["", short],
        },
    },
}
for c in reality["settings"]["clients"]:
    if not c.get("flow"):
        c["flow"] = "xtls-rprx-vision"
cfg["inbounds"].append(reality)
Path("/tmp/xray_candidate.json").write_text(
    json.dumps(cfg, ensure_ascii=False, indent=2)
)
print("reality clients", len(clients))
PY

sudo xray run -test -c /tmp/xray_candidate.json
if [ -f /etc/nginx/qooq_stream.conf ]; then
  sudo cp -a /etc/nginx/qooq_stream.conf /etc/nginx/qooq_stream.conf.bak.pre_reality
fi
sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
if ! sudo nginx -t; then
  echo "nginx -t failed, restoring stream"
  if [ -f /etc/nginx/qooq_stream.conf.bak.pre_reality ]; then
    sudo cp -a /etc/nginx/qooq_stream.conf.bak.pre_reality /etc/nginx/qooq_stream.conf
  fi
  exit 1
fi
sudo cp /tmp/xray_candidate.json "$CFG"
sudo systemctl restart xray
sleep 2
systemctl is-active xray
ss -lntp | grep -E '10443|18443|11443|443' || true
sudo systemctl reload nginx
sleep 1
systemctl is-active nginx
ss -lntp | grep -q 127.0.0.1:11443
ss -lntp | grep -q 127.0.0.1:10443
ss -lntp | grep -q ':443'
echo CUTOVER_OK
cat /tmp/reality_pub.txt
cat /tmp/reality_short.txt
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    sftp.put(str(PROJECT / "src/services/xray_sync.py"), f"{REMOTE}/src/services/xray_sync.py")
    with sftp.file("/tmp/qooq_stream.conf", "w") as f:
        f.write(STREAM)
    with sftp.file("/tmp/qooq_reality.sh", "w") as f:
        f.write(SH)
    sftp.close()

    def run(cmd, t=180):
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        print(out)
        if err.strip():
            print(err[-3000:])
        return code, out

    run(
        "scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no "
        "/tmp/qooq_stream.conf /tmp/qooq_reality.sh adminka@51.250.32.123:/tmp/"
    )
    code, out = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'sudo bash /tmp/qooq_reality.sh'"
    )
    if code != 0 or "CUTOVER_OK" not in out:
        print("FAILED — rollback xray")
        run(
            "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
            "'sudo cp -a /usr/local/etc/xray/config.json.bak.pre_reality /usr/local/etc/xray/config.json; "
            "sudo systemctl restart xray; sleep 2; systemctl is-active xray; ss -lntp | grep 443'"
        )
        client.close()
        return 1

    code, keys_out = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'cat /tmp/reality_pub.txt; echo ---; cat /tmp/reality_short.txt'"
    )
    parts = keys_out.strip().split("---")
    pub = parts[0].strip()
    short = parts[1].strip() if len(parts) > 1 else ""
    print("PUB", pub, "SHORT", short)

    template = {
        "remarks": "{remarks}",
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "51.250.32.123",
                            "port": 443,
                            "users": [
                                {
                                    "id": "{uuid}",
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "fingerprint": "chrome",
                        "serverName": REALITY_SNI,
                        "publicKey": pub,
                        "shortId": short,
                        "spiderX": "",
                    },
                },
                "tag": "proxy",
            },
            {"protocol": "freedom", "tag": "direct"},
        ],
    }
    tpl_json = json.dumps(template, ensure_ascii=False)

    sftp = client.open_sftp()
    with sftp.file("/tmp/reality_template.json", "w") as f:
        f.write(tpl_json)
    sftp.close()
    run(
        "scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no "
        "/tmp/reality_template.json adminka@51.250.32.123:/tmp/"
    )
    run("cp /tmp/reality_template.json /tmp/reality_template.json")

    py = f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio
import json
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.config import get_settings
from src.core.enums import VpnConfigType
from src.models import VpnConfig, VpnServer, Subscription
from src.services.vpn_config import VPN_HOST, build_credential_share_link
from src.services.vpn_config_store import VpnConfigStore
from src.services.config_credentials import ConfigCredentialService
from src.services import SubscriptionService
from src.api.routes.sub_feed import _credential_remark

NAME = {REALITY_CONFIG_NAME!r}
TOKEN = {TOKEN!r}
tpl = open("/tmp/reality_template.json", encoding="utf-8").read()
assert "{{uuid}}" in tpl

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        entry = (await session.execute(select(VpnServer).where(VpnServer.host == VPN_HOST))).scalar_one()
        cfg = (await session.execute(select(VpnConfig).where(VpnConfig.name == NAME))).scalar_one_or_none()
        store = VpnConfigStore(session)
        if cfg:
            cfg.config_template = tpl
            cfg.is_active = True
            cfg.server_id = entry.id
            print("updated", cfg.id)
        else:
            cfg = await store.create_config(entry.id, NAME, VpnConfigType.XRAY_JSON, tpl, False)
            print("created", cfg.id)
        sub = (await session.execute(select(Subscription).where(Subscription.subscription_token == TOKEN))).scalar_one()
        await ConfigCredentialService(session, settings).ensure_credentials(sub)
        print("sync", await SubscriptionService(session, settings).sync_xray_clients())
        await session.commit()
        for c in await ConfigCredentialService(session, settings).list_active(sub.id):
            if c.vpn_config and c.vpn_config.name == NAME:
                print("REALITY_VLESS=" + build_credential_share_link(
                    c.client_uuid, c.vpn_config.config_type.value,
                    c.vpn_config.config_template, _credential_remark(c)))
        print("SUB_URL=https://keys.qooqvpn.ru/sub/" + TOKEN)

asyncio.run(main())
PY
systemctl restart qooq-api
"""
    code, out = run(py, t=240)
    time.sleep(3)
    run(
        f"curl -sS http://127.0.0.1:8000/sub/{TOKEN} | python3 -c \""
        "import sys,base64,urllib.parse\\n"
        "body=base64.b64decode(sys.stdin.buffer.read().strip()).decode()\\n"
        "for l in body.splitlines():\\n"
        " n=urllib.parse.unquote(l.rsplit('#',1)[-1])\\n"
        " if 'Tinkoff' in n or n.strip().endswith('LTE'):\\n"
        "  print(n); print(l[:180]+'...')\\n"
        "\""
    )
    client.close()
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
