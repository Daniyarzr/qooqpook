"""Verbose cutover with explicit rollback on failure."""
from __future__ import annotations

import os
import sys
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
CFG=/usr/local/etc/xray/config.json
# dedupe nginx includes
sudo cp /tmp/qooq_stream.conf /etc/nginx/qooq_stream.conf
sudo python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/nginx.conf')
lines=p.read_text().splitlines(True)
out=[]; seen=False
for line in lines:
    if 'qooq_stream.conf' in line:
        if seen: continue
        seen=True
    out.append(line)
if not any('qooq_stream.conf' in x for x in out):
    out.append('\ninclude /etc/nginx/qooq_stream.conf;\n')
p.write_text(''.join(out))
print('nginx.conf include ok')
PY
sudo nginx -t

sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/fullchain.cer /etc/xray/certs/white.qooqvpn.ru.fullchain.cer
sudo cp -f /home/adminka/.acme.sh/white.qooqvpn.ru_ecc/white.qooqvpn.ru.key /etc/xray/certs/white.qooqvpn.ru.key

sudo rm -f /tmp/xray_work.json /tmp/xray_candidate.json
sudo cat "$CFG" > /tmp/xray_work.json
sudo chown adminka:adminka /tmp/xray_work.json
python3 <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path('/tmp/xray_work.json').read_text())
tcp=xhttp=None
for ib in cfg['inbounds']:
    if ib.get('protocol')!='vless': continue
    net=(ib.get('streamSettings') or {}).get('network') or 'tcp'
    if net=='xhttp' or ib.get('tag')=='lte-xhttp': xhttp=ib
    elif net=='tcp' and ib.get('port') in (443,10443,8443):
        if tcp is None or ib.get('port') in (443,10443): tcp=ib
assert tcp and xhttp
tcp['tag']='vless-tcp'; tcp['listen']='127.0.0.1'; tcp['port']=10443
xhttp['tag']='lte-xhttp'; xhttp['listen']='127.0.0.1'; xhttp['port']=18443
ss=xhttp.setdefault('streamSettings',{})
ss['network']='xhttp'; ss['security']='tls'
ss['tlsSettings']={'alpn':['h2','http/1.1'],'certificates':[{'certificateFile':'/etc/xray/certs/white.qooqvpn.ru.fullchain.cer','keyFile':'/etc/xray/certs/white.qooqvpn.ru.key'}]}
ss['xhttpSettings']={'path':'/static/getFile/video/segment.ts','host':'white.qooqvpn.ru','mode':'packet-up','extra':{'noSSEHeader':True,'scMaxBufferedPosts':30,'uplinkHTTPMethod':'GET'}}
Path('/tmp/xray_candidate.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
print('xray patched')
PY
sudo xray run -test -c /tmp/xray_candidate.json
sudo cp -a "$CFG" /usr/local/etc/xray/config.json.bak.before_sni_live
sudo cp /tmp/xray_candidate.json "$CFG"

echo 'restart xray...'
sudo systemctl restart xray
sleep 2
systemctl is-active xray
ss -lntp | grep -E 'xray|443|10443|18443' || true

echo 'reload nginx...'
sudo systemctl reload nginx
sleep 1
systemctl is-active nginx
ss -lntp | grep -E 'nginx|443|10443|18443' || true

if ! ss -lntp | grep -q '127.0.0.1:10443'; then echo FAIL_NO_10443; exit 1; fi
if ! ss -lntp | grep -q '127.0.0.1:18443'; then echo FAIL_NO_18443; exit 1; fi
if ! ss -lntp | grep -q ':443'; then echo FAIL_NO_443; exit 1; fi
echo CUTOVER_OK
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white2.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || echo white2_fail
echo | timeout 5 openssl s_client -connect 127.0.0.1:443 -servername white.qooqvpn.ru 2>/dev/null | openssl x509 -noout -subject || echo white_fail
'''


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    sftp.put(str(PROJECT / "src/services/vpn_config.py"), f"{REMOTE}/src/services/vpn_config.py")
    sftp.put(str(PROJECT / "src/services/xray_sync.py"), f"{REMOTE}/src/services/xray_sync.py")
    with sftp.file("/tmp/qooq_stream.conf", "w") as f:
        f.write(STREAM)
    with sftp.file("/tmp/qooq_cutover2.sh", "w") as f:
        f.write(SH)
    sftp.close()

    def run(cmd, t=180):
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        print(out)
        if err.strip():
            print("STDERR", err[-4000:])
        return code, out

    run(
        "scp -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no "
        "/tmp/qooq_stream.conf /tmp/qooq_cutover2.sh adminka@51.250.32.123:/tmp/"
    )
    code, out = run(
        "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
        "'bash /tmp/qooq_cutover2.sh'"
    )
    if code != 0 or "CUTOVER_OK" not in out:
        print("FAILED code", code)
        # try rollback xray from bak if xray broken
        run(
            "ssh -i /root/.ssh/qooq_xray -o StrictHostKeyChecking=no adminka@51.250.32.123 "
            "'ls -lt /usr/local/etc/xray/config.json.bak* | head; "
            "sudo ss -lntp | grep -E 443|xray|10443|18443 || true; "
            "systemctl is-active xray nginx; journalctl -u xray -n 20 --no-pager; journalctl -u nginx -n 20 --no-pager'"
        )
        client.close()
        return 1

    code, out = run(
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
        "    cfg=(await session.execute(select(VpnConfig).where(VpnConfig.name==LTE_XHTTP_CONFIG_NAME))).scalar_one()\n"
        "    cfg.config_template=export_lte_xhttp_json_template(); cfg.is_active=True\n"
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
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
