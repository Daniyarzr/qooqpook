"""Finish SNI mux cutover (cert already issued)."""
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

REMOTE_SH = r'''
set -euo pipefail
if [ -f /usr/lib/nginx/modules/ngx_stream_module.so ]; then
  echo 'load_module /usr/lib/nginx/modules/ngx_stream_module.so;' | sudo tee /etc/nginx/modules-enabled/50-mod-stream.conf >/dev/null
fi
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key
sudo chmod 644 /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo chmod 600 /etc/xray/certs/white.qooqvpn.ru.key

CFG=/usr/local/etc/xray/config.json
BK=/usr/local/etc/xray/config.json.bak.sni443_final
sudo cp -a "$CFG" "$BK"
echo BACKUP=$BK

sudo rm -f /tmp/xray_work.json /tmp/xray_candidate.json
sudo cat "$CFG" > /tmp/xray_work.json
sudo chown adminka:adminka /tmp/xray_work.json
python3 <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path('/tmp/xray_work.json').read_text())
tcp=xhttp=None
for ib in cfg['inbounds']:
    if ib.get('protocol')!='vless':
        continue
    net=(ib.get('streamSettings') or {}).get('network') or 'tcp'
    if net=='xhttp' or ib.get('tag')=='lte-xhttp':
        xhttp=ib
    elif net=='tcp' and ib.get('port') in (443,10443,8443):
        if tcp is None or ib.get('port') in (443,10443):
            tcp=ib
if not tcp or not xhttp:
    raise SystemExit('missing inbounds')
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
  'alpn':['h2','http/1.1'],
  'certificates':[{
    'certificateFile':'/etc/xray/certs/white.qooqvpn.ru.fullchain.cer',
    'keyFile':'/etc/xray/certs/white.qooqvpn.ru.key',
  }],
}
ss['xhttpSettings']={
  'path':'/static/getFile/video/segment.ts',
  'host':'white.qooqvpn.ru',
  'mode':'packet-up',
  'extra':{'noSSEHeader':True,'scMaxBufferedPosts':30,'uplinkHTTPMethod':'GET'},
}
Path('/tmp/xray_candidate.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
print('patched')
PY
sudo xray run -test -c /tmp/xray_candidate.json
sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
grep -q qooq_stream.conf /etc/nginx/nginx.conf || printf '\ninclude /etc/nginx/qooq_stream.conf;\n' | sudo tee -a /etc/nginx/nginx.conf >/dev/null
sudo nginx -t
sudo cp /tmp/xray_candidate.json "$CFG"
sudo systemctl restart xray
sleep 1
systemctl is-active --quiet xray
ss -lntp | grep -E '10443|18443' || true
sudo systemctl reload nginx || sudo systemctl restart nginx
sleep 1
systemctl is-active --quiet nginx
ss -lntp | grep -E ':443|:10443|:18443' || true
ss -lntp | grep -q 10443
ss -lntp | grep -q 18443
ss -lntp | grep -q ':443'
echo CUTOVER_OK
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || true
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || true
'''


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    sftp.put(str(PROJECT / "src/services/vpn_config.py"), f"{REMOTE}/src/services/vpn_config.py")
    sftp.put(str(PROJECT / "src/services/xray_sync.py"), f"{REMOTE}/src/services/xray_sync.py")
    with sftp.file("/tmp/qooq_stream.conf", "w") as fh:
        fh.write(STREAM)
    with sftp.file("/tmp/qooq_cutover.sh", "w") as fh:
        fh.write(REMOTE_SH)
    sftp.close()

    def run(cmd, timeout=180):
        print("$", cmd[:80])
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        print(out)
        if err.strip():
            print(err[-3000:])
        return code, out

    run(
        "scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no "
        "/tmp/qooq_stream.conf /tmp/qooq_cutover.sh adminka@51.250.32.123:/tmp/"
    )
    code, out = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'bash /tmp/qooq_cutover.sh'"
    )
    if code != 0 or "CUTOVER_OK" not in out:
        print("CUTOVER FAILED")
        client.close()
        return 1

    code, out = run(
        f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.config import get_settings
from src.models import VpnConfig, Subscription
from src.services.vpn_config import LTE_XHTTP_CONFIG_NAME, export_lte_xhttp_json_template, build_credential_share_link
from src.services.config_credentials import ConfigCredentialService
from src.services import SubscriptionService
from src.api.routes.sub_feed import _credential_remark
TOKEN="{TOKEN}"
async def main():
    settings=get_settings()
    async with async_session_factory() as session:
        cfg=(await session.execute(select(VpnConfig).where(VpnConfig.name==LTE_XHTTP_CONFIG_NAME))).scalar_one()
        cfg.config_template=export_lte_xhttp_json_template(); cfg.is_active=True
        sub=(await session.execute(select(Subscription).where(Subscription.subscription_token==TOKEN))).scalar_one()
        await ConfigCredentialService(session, settings).ensure_credentials(sub)
        print('sync', await SubscriptionService(session, settings).sync_xray_clients())
        await session.commit()
        for c in await ConfigCredentialService(session, settings).list_active(sub.id):
            if c.vpn_config and c.vpn_config.name==LTE_XHTTP_CONFIG_NAME:
                print('LTE_VLESS='+build_credential_share_link(c.client_uuid, c.vpn_config.config_type.value, c.vpn_config.config_template, _credential_remark(c)))
        print('SUB_URL=https://keys.qooqvpn.ru/sub/'+TOKEN)
asyncio.run(main())
PY
systemctl restart qooq-api
"""
    )
    time.sleep(3)
    run(
        f"""
curl -sS http://127.0.0.1:8000/sub/{TOKEN} | python3 -c "
import sys,base64,urllib.parse
body=base64.b64decode(sys.stdin.buffer.read().strip()).decode()
for l in body.splitlines():
 n=urllib.parse.unquote(l.rsplit('#',1)[-1])
 if n.strip().endswith('LTE') and 'Россия' not in n and 'Швеция' not in n:
  print(n); print(l); print('host', l.split('@',1)[1].split('?',1)[0])
"
echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
echo | timeout 5 openssl s_client -connect 51.250.32.123:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject
"""
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
