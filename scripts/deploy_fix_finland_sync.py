"""Deploy Finland QooQ sync fix and resync Xray."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/services/vpn_config.py",
    "src/services/xray_sync.py",
    "src/services/vpn_servers_sync.py",
]


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

    def run(cmd: str, timeout: int = 180) -> None:
        print("$", cmd[:100])
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        print(stdout.read().decode("utf-8", errors="replace"))
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            print(err[-2000:])

    run(
        f"cd {REMOTE} && .venv/bin/python - <<'PY'\n"
        "import asyncio\n"
        "from src.core.config import get_settings\n"
        "from src.db.session import async_session_factory\n"
        "from src.services import SubscriptionService\n"
        "from src.services.xray_sync import _split_clients_by_config\n"
        "from src.services.config_credentials import ConfigCredentialService\n\n"
        "async def main():\n"
        "    settings = get_settings()\n"
        "    async with async_session_factory() as session:\n"
        "        creds = await ConfigCredentialService(session, settings).get_all_for_active_subscriptions()\n"
        "        tunnel, panel = _split_clients_by_config(creds)\n"
        "        print('tunnel', len(tunnel), 'panel', len(panel))\n"
        "        for c in panel:\n"
        "            print(' panel uuid', c.client_uuid, 'email', c.email)\n"
        "        ok = await SubscriptionService(session, settings).sync_xray_clients()\n"
        "        await session.commit()\n"
        "        print('sync_ok', ok)\n"
        "asyncio.run(main())\n"
        "PY"
    )
    run(
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "cfg=json.loads(Path('/usr/local/etc/xray/config.json').read_text())\n"
        "for ib in cfg.get('inbounds',[]):\n"
        "  if ib.get('port')==10086:\n"
        "    clients=ib.get('settings',{}).get('clients',[])\n"
        "    print('panel clients now', len(clients))\n"
        "    for cl in clients:\n"
        "      print(' ', cl.get('email'), cl.get('id'))\n"
        "PY"
    )
    run("systemctl is-active xray; ss -lntp | grep 10086")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
