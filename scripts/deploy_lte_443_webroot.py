"""Issue white.qooqvpn.ru cert via nginx webroot, then SNI mux cutover to :443."""
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


def run(client, cmd, timeout=180):
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

    print("=== Issue cert + cutover ===")
    out, err, code = run(
        client,
        r'''
set -e
scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no /tmp/qooq_stream.conf adminka@51.250.32.123:/tmp/qooq_stream.conf
ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 'bash -s' <<'EOS'
set -euo pipefail

# stream module
if [ -f /usr/lib/nginx/modules/ngx_stream_module.so ]; then
  echo 'load_module /usr/lib/nginx/modules/ngx_stream_module.so;' | sudo tee /etc/nginx/modules-enabled/50-mod-stream.conf >/dev/null
fi

# webroot challenge path
sudo mkdir -p /var/www/html/.well-known/acme-challenge
echo ok | sudo tee /var/www/html/.well-known/acme-challenge/ping >/dev/null

# issue/renew white.qooqvpn.ru
export HOME=/home/adminka
ACME=/home/adminka/.acme.sh/acme.sh
# remove broken incomplete order if needed
if [ ! -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer ]; then
  sudo -u adminka bash -lc "$ACME --issue -d white.qooqvpn.ru -w /var/www/html --ecc --force --server letsencrypt" || \
  sudo -u adminka bash -lc "$ACME --issue -d white.qooqvpn.ru -w /var/www/html --force --server letsencrypt"
fi
ls -la /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/
test -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer
test -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key

sudo mkdir -p /etc/xray/certs
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
sudo chmod 644 /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo chmod 600 /etc/xray/certs/white.qooqvpn.ru.key
sudo openssl x509 -in /etc/xray/certs/white.qooqvpn.ru.fullchain.cer -noout -subject -dates
echo CERT_OK

CFG=/usr/local/etc/xray/config.json
BK=/usr/local/etc/xray/config.json.bak.sni443_$(date +%Y%m%d_%H%M%S)
sudo cp -a "$CFG" "$BK"
sudo cp -a /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak.sni443_$(date +%Y%m%d_%H%M%S)
echo BACKUP=$BK

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
    if net=='tcp' and ib.get('port') in (443, 10443, 8443):
        # prefer current public tcp
        if tcp is None or ib.get('port') in (443, 10443):
            tcp=ib
    if ib.get('tag')=='lte-xhttp' or net=='xhttp':
        xhttp=ib
# refine tcp: exact tcp network
tcp=None
for ib in cfg['inbounds']:
    if ib.get('protocol')!='vless':
        continue
    net=(ib.get('streamSettings') or {}).get('network') or 'tcp'
    if net=='tcp' and ib.get('port') in (443, 10443):
        tcp=ib
        break
if not tcp:
    for ib in cfg['inbounds']:
        if ib.get('protocol')=='vless' and ((ib.get('streamSettings') or {}).get('network') or 'tcp')=='tcp' and ib.get('port') not in (10085,):
            tcp=ib; break
if not tcp or not xhttp:
    raise SystemExit(f'missing tcp={bool(tcp)} xhttp={bool(xhttp)}')

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
print('patched', tcp['port'], xhttp['port'])
PY

sudo xray run -test -c /tmp/xray_candidate.json
echo XRAY_TEST_OK

sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
if ! grep -q 'qooq_stream.conf' /etc/nginx/nginx.conf; then
  printf '\ninclude /etc/nginx/qooq_stream.conf;\n' | sudo tee -a /etc/nginx/nginx.conf >/dev/null
fi
sudo nginx -t
echo NGINX_TEST_OK

# cutover
sudo cp /tmp/xray_candidate.json "$CFG"
sudo systemctl restart xray
sleep 1
systemctl is-active --quiet xray
ss -lntp | grep -E '10443|18443'
sudo systemctl reload nginx || sudo systemctl restart nginx
sleep 1
systemctl is-active --quiet nginx
ss -lntp | grep -E ':443|:10443|:18443'

ss -lntp | grep 10443 >/dev/null
ss -lntp | grep 18443 >/dev/null
ss -lntp | grep ':443' >/dev/null
echo CUTOVER_OK

echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || true
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || true
EOS
''',
        timeout=180,
    )
    print(out)
    if err.strip():
        print("ERR", err[-4000:])
    if code != 0 or "CUTOVER_OK" not in out:
        print("FAILED")
        client.close()
        return 1

    print("=== Update LTE profile ===")
    out, err, code = run(
        client,
        f'''
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio, json
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.config import get_settings
from src.models import VpnConfig, Subscription
from src.services.vpn_config import LTE_XHTTP_CONFIG_NAME, export_lte_xhttp_json_template, build_credential_share_link
from src.services.config_credentials import ConfigCredentialService
from src.services import SubscriptionService
from src.api.routes.sub_feed import _credential_remark

TOKEN = "{TOKEN}"

async def main():
    settings = get_settings()
    async with async_session_factory() as session:
        cfg = (await session.execute(select(VpnConfig).where(VpnConfig.name == LTE_XHTTP_CONFIG_NAME))).scalar_one()
        cfg.config_template = export_lte_xhttp_json_template()
        cfg.is_active = True
        sub = (await session.execute(select(Subscription).where(Subscription.subscription_token == TOKEN))).scalar_one()
        await ConfigCredentialService(session, settings).ensure_credentials(sub)
        ok = await SubscriptionService(session, settings).sync_xray_clients()
        await session.commit()
        print("sync_ok", ok)
        for c in await ConfigCredentialService(session, settings).list_active(sub.id):
            if c.vpn_config and c.vpn_config.name == LTE_XHTTP_CONFIG_NAME:
                print("LTE_VLESS=" + build_credential_share_link(
                    c.client_uuid, c.vpn_config.config_type.value,
                    c.vpn_config.config_template, _credential_remark(c)))
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
curl -sS "http://127.0.0.1:8000/sub/{TOKEN}" | python3 -c "
import sys,base64,urllib.parse
body=base64.b64decode(sys.stdin.buffer.read().strip()).decode()
for l in body.splitlines():
  n=urllib.parse.unquote(l.rsplit('#',1)[-1])
  if n.strip()=='🇷🇺 LTE' or n.endswith(' LTE') and 'Россия' not in n and 'Швеция' not in n:
    print(n)
    print(l)
    print('host', l.split('@',1)[1].split('?',1)[0])
"
echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
''',
    )
    print(out)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
