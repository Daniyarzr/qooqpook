"""Move LTE xHTTP to :443 via nginx SNI mux. Keep white2 TCP for existing clients.

SNI map:
  white2.qooqvpn.ru -> 127.0.0.1:10443 (VLESS TCP TLS)  [production]
  white.qooqvpn.ru  -> 127.0.0.1:18443 (VLESS xHTTP TLS) [LTE bypass]
  default           -> 127.0.0.1:10443
"""
from __future__ import annotations

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
]


NGINX_STREAM = r'''
# QooQ SNI multiplex — managed by deploy_lte_443_sni_mux.py
stream {
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
'''


def run(client, cmd, timeout=120):
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
    with sftp.file("/tmp/qooq_stream.conf", "w") as fh:
        fh.write(NGINX_STREAM)
    sftp.close()

    print("=== Cutover on Yandex ===")
    out, err, code = run(
        client,
        r'''
set -e
scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no /tmp/qooq_stream.conf adminka@51.250.32.123:/tmp/qooq_stream.conf
ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 'bash -s' <<'EOS'
set -euo pipefail

# 0) enable stream module
if [ -f /usr/lib/nginx/modules/ngx_stream_module.so ]; then
  echo 'load_module /usr/lib/nginx/modules/ngx_stream_module.so;' | sudo tee /etc/nginx/modules-enabled/50-mod-stream.conf >/dev/null
fi

# 1) certs for white.qooqvpn.ru
sudo mkdir -p /etc/xray/certs
if [ -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer ]; then
  sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
  sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
elif [ -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.cer ]; then
  sudo cat /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.cer \
    /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/ca.cer 2>/dev/null \
    | sudo tee /etc/xray/certs/white.qooqvpn.ru.fullchain.cer >/dev/null
  sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
else
  echo 'NO_WHITE_CERT — issue via acme'
  sudo /home/adminka/.acme.sh/acme.sh --issue -d white.qooqvpn.ru --ecc --standalone --httpport 80 || true
  sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
  sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
fi
sudo chmod 644 /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo chmod 600 /etc/xray/certs/white.qooqvpn.ru.key
sudo openssl x509 -in /etc/xray/certs/white.qooqvpn.ru.fullchain.cer -noout -subject || exit 1
echo CERT_OK

# 2) backup
CFG=/usr/local/etc/xray/config.json
BK=/usr/local/etc/xray/config.json.bak.sni443_$(date +%Y%m%d_%H%M%S)
NGX_BK=/etc/nginx/nginx.conf.bak.sni443_$(date +%Y%m%d_%H%M%S)
sudo cp -a "$CFG" "$BK"
sudo cp -a /etc/nginx/nginx.conf "$NGX_BK"
echo BACKUP_XRAY=$BK
echo BACKUP_NGX=$NGX_BK

# 3) patch xray listens to localhost
sudo cat "$CFG" > /tmp/xray_work.json
python3 - <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path('/tmp/xray_work.json').read_text())
tcp=xhttp=None
for ib in cfg['inbounds']:
    if ib.get('protocol')!='vless':
        continue
    net=(ib.get('streamSettings') or {}).get('network') or 'tcp'
    if ib.get('port') in (443, 10443) and net=='tcp':
        tcp=ib
    if ib.get('tag')=='lte-xhttp' or net=='xhttp' or ib.get('port') in (8443, 18443):
        xhttp=ib
if not tcp or not xhttp:
    raise SystemExit(f'missing inbounds tcp={bool(tcp)} xhttp={bool(xhttp)}')

tcp['tag']='vless-tcp'
tcp['listen']='127.0.0.1'
tcp['port']=10443

xhttp['tag']='lte-xhttp'
xhttp['listen']='127.0.0.1'
xhttp['port']=18443
ss=xhttp.setdefault('streamSettings', {})
ss['network']='xhttp'
ss['security']='tls'
ss['tlsSettings']={
  'alpn': ['h2', 'http/1.1'],
  'certificates': [{
    'certificateFile': '/etc/xray/certs/white.qooqvpn.ru.fullchain.cer',
    'keyFile': '/etc/xray/certs/white.qooqvpn.ru.key',
  }],
}
ss['xhttpSettings']={
  'path': '/static/getFile/video/segment.ts',
  'host': 'white.qooqvpn.ru',
  'mode': 'packet-up',
  'extra': {'noSSEHeader': True, 'scMaxBufferedPosts': 30, 'uplinkHTTPMethod': 'GET'},
}
Path('/tmp/xray_candidate.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
print('XRAY_PATCHED')
PY

sudo xray run -test -c /tmp/xray_candidate.json
echo XRAY_TEST_OK

# 4) prepare nginx: keep http {}, add include stream
sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
# ensure main nginx.conf includes stream file at top level (not inside http)
if ! grep -q 'qooq_stream.conf' /etc/nginx/nginx.conf; then
  echo 'include /etc/nginx/qooq_stream.conf;' | sudo tee -a /etc/nginx/nginx.conf >/dev/null
fi
sudo nginx -t
echo NGINX_TEST_OK

# 5) cutover: xray first (frees :443), then nginx reload
sudo cp /tmp/xray_candidate.json "$CFG"
sudo systemctl restart xray
sleep 1
systemctl is-active --quiet xray
ss -lntp | grep -E '10443|18443' || true
# 443 should be free now
sudo systemctl reload nginx || sudo systemctl restart nginx
sleep 1
systemctl is-active --quiet nginx
ss -lntp | grep -E ':443|:10443|:18443' || true

# 6) smoke: local connect via SNI using openssl
timeout 5 bash -c 'echo | openssl s_client -connect 127.0.0.1:443 -servername white2.qooqvpn.ru 2>/dev/null | head -3' || true
timeout 5 bash -c 'echo | openssl s_client -connect 127.0.0.1:443 -servername white.qooqvpn.ru 2>/dev/null | head -3' || true

# verify backends
ss -lntp | grep 10443 >/dev/null && echo TCP_BACKEND_OK || { echo TCP_BACKEND_FAIL; exit 1; }
ss -lntp | grep 18443 >/dev/null && echo XHTTP_BACKEND_OK || { echo XHTTP_BACKEND_FAIL; exit 1; }
ss -lntp | grep ':443' >/dev/null && echo PORT443_OK || { echo PORT443_FAIL; exit 1; }
echo CUTOVER_OK
EOS
''',
        timeout=120,
    )
    print(out)
    if err.strip():
        print("ERR", err[-3000:])
    if code != 0 or "CUTOVER_OK" not in out:
        print("FAILED — attempting rollback note")
        client.close()
        return 1

    # Update code constants + DB template to white:443
    print("=== Update LTE profile to white.qooqvpn.ru:443 ===")
    out, err, code = run(
        client,
        f'''
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio, json
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.config import get_settings
from src.models import VpnConfig, Subscription
from src.services.vpn_config import LTE_XHTTP_CONFIG_NAME, VPN_HOST, VPN_SNI, build_credential_share_link
from src.services.config_credentials import ConfigCredentialService
from src.services import SubscriptionService
from src.api.routes.sub_feed import _credential_remark

TOKEN = "{TOKEN}"
LTE_SNI = "white.qooqvpn.ru"

def make_template():
    return json.dumps({{
      "remarks": "{{remarks}}",
      "log": {{"loglevel": "warning"}},
      "dns": {{"queryStrategy": "UseIPv4", "servers": ["1.1.1.1", "1.0.0.1"]}},
      "inbounds": [{{
        "listen": "127.0.0.1", "port": 10808, "protocol": "socks",
        "settings": {{"auth": "noauth", "udp": True}}, "tag": "socks"
      }}],
      "outbounds": [{{
        "protocol": "vless",
        "settings": {{"vnext": [{{
          "address": LTE_SNI,
          "port": 443,
          "users": [{{"encryption": "none", "id": "{{uuid}}", "flow": ""}}]
        }}]}},
        "streamSettings": {{
          "network": "xhttp",
          "security": "tls",
          "tlsSettings": {{
            "alpn": ["h2", "http/1.1"],
            "fingerprint": "firefox",
            "serverName": LTE_SNI
          }},
          "xhttpSettings": {{
            "host": LTE_SNI,
            "mode": "packet-up",
            "path": "/static/getFile/video/segment.ts",
            "extra": {{"noSSEHeader": True, "scMaxBufferedPosts": 30, "uplinkHTTPMethod": "GET"}}
          }}
        }},
        "tag": "proxy"
      }}, {{"protocol": "freedom", "tag": "direct"}}, {{"protocol": "blackhole", "tag": "block"}}],
      "routing": {{"domainStrategy": "IPIfNonMatch", "rules": []}}
    }}, ensure_ascii=False, indent=2)

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        cfg = (await session.execute(
            select(VpnConfig).where(VpnConfig.name == LTE_XHTTP_CONFIG_NAME)
        )).scalar_one_or_none()
        if not cfg:
            raise SystemExit("LTE config missing")
        cfg.config_template = make_template()
        cfg.is_active = True
        sub = (await session.execute(
            select(Subscription).where(Subscription.subscription_token == TOKEN)
        )).scalar_one()
        await ConfigCredentialService(session, settings).ensure_credentials(sub)
        ok = await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print("sync_ok", ok)
        active = await ConfigCredentialService(session, settings).list_active(sub.id)
        for c in active:
            if c.vpn_config and c.vpn_config.name == LTE_XHTTP_CONFIG_NAME:
                link = build_credential_share_link(
                    c.client_uuid, c.vpn_config.config_type.value,
                    c.vpn_config.config_template, _credential_remark(c),
                )
                print("LTE_VLESS=" + link)
                break
        print("SUB_URL=https://keys.qooqvpn.ru/sub/" + TOKEN)

asyncio.run(main())
PY
systemctl restart qooq-api
''',
        timeout=180,
    )
    print(out)
    if err.strip():
        print(err[-2000:])

    time.sleep(3)
    out, _, _ = run(
        client,
        f'''
curl -sS -o /tmp/sub_out.txt -w "HTTP %{{http_code}}\\n" http://127.0.0.1:8000/sub/{TOKEN}
python3 - <<'PY'
import base64, urllib.parse
raw=open('/tmp/sub_out.txt','rb').read().strip()
body=base64.b64decode(raw).decode()
for l in body.splitlines():
  name=urllib.parse.unquote(l.rsplit('#',1)[-1])
  if 'LTE' in name and 'Россия' not in name and 'Швеция' not in name:
    print('NAME', name)
    print('LINK', l)
    print('HOST', l.split('@',1)[1].split('?',1)[0])
PY
# external checks
timeout 5 bash -c 'echo | openssl s_client -connect 51.250.32.123:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject' || echo white2_tls_fail
timeout 5 bash -c 'echo | openssl s_client -connect 51.250.32.123:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject' || echo white_tls_fail
''',
    )
    print(out)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
