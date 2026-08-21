"""Safe SNI mux cutover: fix cert perms, localhost xray backends, nginx stream."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
TOKEN = "RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc"

STREAM = """stream {
    map $ssl_preread_server_name $qooq_backend {
        white.qooqvpn.ru   127.0.0.1:18443;
        white2.qooqvpn.ru  127.0.0.1:10443;
        default            127.0.0.1:10443;
    }
    server {
        listen 443 reuseport;
        listen [::]:443 reuseport;
        proxy_pass $qooq_backend;
        ssl_preread on;
        proxy_connect_timeout 5s;
        proxy_timeout 300s;
    }
}
"""

SH = r'''
set -euxo pipefail

# 1) certs readable by nobody (same as white2 key)
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
sudo chmod 644 /etc/xray/certs/white.qooqvpn.ru.fullchain.cer /etc/xray/certs/white.qooqvpn.ru.key
sudo ls -la /etc/xray/certs/

# 2) stream module + nginx include (deduped)
if [ -f /usr/share/nginx/modules-available/mod-stream.conf ]; then
  sudo ln -sfn /usr/share/nginx/modules-available/mod-stream.conf /etc/nginx/modules-enabled/50-mod-stream.conf
fi
sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
sudo python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/nginx.conf')
lines=[ln for ln in p.read_text().splitlines(True) if 'qooq_stream.conf' not in ln]
lines.append('\ninclude /etc/nginx/qooq_stream.conf;\n')
p.write_text(''.join(lines))
PY
sudo nginx -t

# 3) build xray config from CURRENT live (tcp :443)
CFG=/usr/local/etc/xray/config.json
sudo cp -a "$CFG" /usr/local/etc/xray/config.json.bak.pre_mux_ok
sudo rm -f /tmp/xray_work.json /tmp/xray_candidate.json
sudo cp "$CFG" /tmp/xray_work.json
sudo chown adminka:adminka /tmp/xray_work.json
python3 <<'PY'
import json, copy
from pathlib import Path
cfg=json.loads(Path('/tmp/xray_work.json').read_text())
tcp=None
for ib in cfg['inbounds']:
    if ib.get('protocol')=='vless' and ((ib.get('streamSettings') or {}).get('network') or 'tcp')=='tcp' and ib.get('port') in (443,10443):
        tcp=ib
        break
assert tcp, 'no tcp inbound'
# remove any old lte-xhttp / 8443
cfg['inbounds']=[ib for ib in cfg['inbounds'] if not (
    ib.get('tag')=='lte-xhttp' or ((ib.get('streamSettings') or {}).get('network')=='xhttp') or ib.get('port') in (8443,18443)
)]
tcp['tag']='vless-tcp'
tcp['listen']='127.0.0.1'
tcp['port']=10443
clients=copy.deepcopy(tcp.get('settings',{}).get('clients',[]))
xhttp={
  'tag':'lte-xhttp',
  'listen':'127.0.0.1',
  'port':18443,
  'protocol':'vless',
  'settings':{'clients':clients,'decryption':'none'},
  'streamSettings':{
    'network':'xhttp',
    'security':'tls',
    'tlsSettings':{
      'alpn':['h2','http/1.1'],
      'certificates':[{
        'certificateFile':'/etc/xray/certs/white.qooqvpn.ru.fullchain.cer',
        'keyFile':'/etc/xray/certs/white.qooqvpn.ru.key',
      }],
    },
    'xhttpSettings':{
      'path':'/static/getFile/video/segment.ts',
      'host':'white.qooqvpn.ru',
      'mode':'packet-up',
      'extra':{'noSSEHeader':True,'scMaxBufferedPosts':30,'uplinkHTTPMethod':'GET'},
    },
  },
}
# insert after tcp
idx=cfg['inbounds'].index(tcp)
cfg['inbounds'].insert(idx+1, xhttp)
Path('/tmp/xray_candidate.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
print('clients', len(clients))
PY
sudo xray run -test -c /tmp/xray_candidate.json

# 4) cutover
sudo cp /tmp/xray_candidate.json "$CFG"
sudo systemctl restart xray
sleep 2
systemctl is-active xray
ss -lntp | grep -E '10443|18443|443' || true
sudo systemctl reload nginx
sleep 1
systemctl is-active nginx
ss -lntp | grep -E 'nginx|:443|10443|18443' || true

ss -lntp | grep -q '127.0.0.1:10443'
ss -lntp | grep -q '127.0.0.1:18443'
ss -lntp | grep -q ':443'
echo CUTOVER_OK
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
'''


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in ("src/services/vpn_config.py", "src/services/xray_sync.py"):
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    with sftp.file("/tmp/qooq_stream.conf", "w") as f:
        f.write(STREAM)
    with sftp.file("/tmp/qooq_mux_safe.sh", "w") as f:
        f.write(SH)
    sftp.close()

    def run(cmd, t=180):
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        print(out)
        if err.strip():
            print(err[-3500:])
        return code, out

    run(
        "scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no "
        "/tmp/qooq_stream.conf /tmp/qooq_mux_safe.sh adminka@51.250.32.123:/tmp/"
    )
    code, out = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'sudo bash /tmp/qooq_mux_safe.sh'"
    )
    if code != 0 or "CUTOVER_OK" not in out:
        print("FAIL — rolling back")
        run(
            "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
            "'sudo bash -s' <<'EOS'\n"
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "p=Path('/etc/nginx/nginx.conf')\n"
            "p.write_text(''.join(ln for ln in p.read_text().splitlines(True) if 'qooq_stream.conf' not in ln))\n"
            "PY\n"
            "nginx -t && systemctl reload nginx || true\n"
            "cp -a /usr/local/etc/xray/config.json.bak.pre_mux_ok /usr/local/etc/xray/config.json\n"
            "systemctl restart xray; sleep 2; systemctl is-active xray; ss -lntp | grep 443\n"
            "EOS"
        )
        client.close()
        return 1

    run(
        f"cd {REMOTE} && .venv/bin/python - <<'PY'\n"
        "import asyncio\n"
        "from sqlalchemy import select\n"
        "from src.db.session import async_session_factory\n"
        "from src.core.config import get_settings\n"
        "from src.models import VpnConfig, Subscription\n"
        "from src.services.vpn_config import LTE_XHTTP_CONFIG_NAME, export_lte_xhttp_json_template, build_credential_share_link\n"
        "from src.services.config_credentials import ConfigCredentialService\n"
        "from src.services import SubscriptionService\n"
        "from src.api.routes.sub_feed import _credential_remark\n"
        f"TOKEN='{TOKEN}'\n"
        "async def main():\n"
        "  s=get_settings()\n"
        "  async with async_session_factory() as session:\n"
        "    cfg=(await session.execute(select(VpnConfig).where(VpnConfig.name==LTE_XHTTP_CONFIG_NAME))).scalar_one_or_none()\n"
        "    if not cfg:\n"
        "      from src.models import VpnServer\n"
        "      from src.core.enums import VpnConfigType\n"
        "      from src.services.vpn_config import VPN_HOST\n"
        "      from src.services.vpn_config_store import VpnConfigStore\n"
        "      entry=(await session.execute(select(VpnServer).where(VpnServer.host==VPN_HOST))).scalar_one()\n"
        "      cfg=await VpnConfigStore(session).create_config(entry.id, LTE_XHTTP_CONFIG_NAME, VpnConfigType.XRAY_JSON, export_lte_xhttp_json_template(), False)\n"
        "    else:\n"
        "      cfg.config_template=export_lte_xhttp_json_template(); cfg.is_active=True\n"
        "    sub=(await session.execute(select(Subscription).where(Subscription.subscription_token==TOKEN))).scalar_one()\n"
        "    await ConfigCredentialService(session,s).ensure_credentials(sub)\n"
        "    print('sync', await SubscriptionService(session,s).sync_xray_clients())\n"
        "    await session.commit()\n"
        "    for c in await ConfigCredentialService(session,s).list_active(sub.id):\n"
        "      if c.vpn_config and c.vpn_config.name==LTE_XHTTP_CONFIG_NAME:\n"
        "        print('LTE_VLESS='+build_credential_share_link(c.client_uuid,c.vpn_config.config_type.value,c.vpn_config.config_template,_credential_remark(c)))\n"
        "    print('SUB_URL=https://keys.qooqvpn.ru/sub/'+TOKEN)\n"
        "asyncio.run(main())\n"
        "PY\n"
        "systemctl restart qooq-api\n"
    )
    time.sleep(3)
    run(
        f"curl -sS http://127.0.0.1:8000/sub/{TOKEN} | python3 -c \""
        "import sys,base64,urllib.parse\n"
        "body=base64.b64decode(sys.stdin.buffer.read().strip()).decode()\n"
        "for l in body.splitlines():\n"
        " n=urllib.parse.unquote(l.rsplit('#',1)[-1])\n"
        " if n.strip().endswith('LTE') and 'Россия' not in n and 'Швеция' not in n:\n"
        "  print(n); print(l)\n"
        "\"\n"
        "echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject\n"
        "echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject\n"
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
