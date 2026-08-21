"""Import configs from jopa.txt into production DB and activate them in subscriptions."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
JOPA = Path(r"C:\Users\Admin\Documents\vpn\jopa.txt")

CODE_FILES = [
    "src/services/vpn_config.py",
    "src/services/vpn_servers_sync.py",
    "src/api/routes/sub_feed.py",
    "src/services/__init__.py",
]


def parse_jopa(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?ms)^(?:(?P<label>[^\n{].*?)\s*-\s*)?(?P<body>\{.*?^\})",
    )
    configs: list[dict] = []
    for match in pattern.finditer(text):
        body = match.group("body")
        data = json.loads(body)
        remark = (data.get("remarks") or match.group("label") or f"Config {len(configs)+1}").strip()
        configs.append({"name": remark, "raw": json.dumps(data, ensure_ascii=False, indent=2)})
    return configs


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    configs = parse_jopa(JOPA)
    print(f"Parsed {len(configs)} configs")
    for c in configs:
        print(" -", c["name"])

    payload = json.dumps(configs, ensure_ascii=False)
    remote_payload = f"{REMOTE}/_jopa_import.json"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    for rel in CODE_FILES:
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    with sftp.file(remote_payload, "w") as fh:
        fh.write(payload)
    sftp.close()

    remote_script = r'''
import asyncio, json
from pathlib import Path
from sqlalchemy import select
from src.db.session import async_session_factory
from src.core.enums import VpnConfigType
from src.models import VpnConfig, VpnServer
from src.services.vpn_config import PANEL_TUNNEL_HOST, xray_config_to_share_link
from src.services.vpn_config_store import VpnConfigStore

IMPORTED = json.loads(Path("/opt/qooq-vpn/_jopa_import.json").read_text(encoding="utf-8"))

async def main():
    async with async_session_factory() as session:
        panel = (await session.execute(
            select(VpnServer).where(VpnServer.host == PANEL_TUNNEL_HOST, VpnServer.is_active.is_(True)).limit(1)
        )).scalar_one_or_none()
        if not panel:
            raise SystemExit("Panel server not found")

        store = VpnConfigStore(session)
        names = {item["name"] for item in IMPORTED}

        # Deactivate previous imported copies with same remarks/names (except system)
        keep_system = {"JSON-конфиг", "Финляндия QooQ VPN 🇫🇮"}
        result = await session.execute(select(VpnConfig))
        for cfg in result.scalars().all():
            if cfg.name in names:
                cfg.is_active = False
                cfg.is_default = False

        created = []
        for item in IMPORTED:
            data = json.loads(item["raw"])
            link = xray_config_to_share_link(data, item["name"])
            if not link:
                print("SKIP no share link:", item["name"])
                continue
            print("LINK OK", item["name"], link[:80] + "...")
            cfg = await store.create_config(
                server_id=panel.id,
                name=item["name"],
                config_type=VpnConfigType.XRAY_JSON,
                config_template=item["raw"],
                is_default=False,
            )
            created.append(cfg.id)

        await session.commit()
        print("CREATED", created)

        # Show active
        result = await session.execute(
            select(VpnConfig.id, VpnConfig.name, VpnConfig.is_active).where(VpnConfig.is_active.is_(True)).order_by(VpnConfig.id)
        )
        print("ACTIVE CONFIGS:")
        for row in result:
            print(" ", row[0], row[1])

asyncio.run(main())
'''
    remote_py = f"{REMOTE}/_import_jopa.py"
    sftp = client.open_sftp()
    with sftp.file(remote_py, "w") as fh:
        fh.write(remote_script)
    sftp.close()

    def run(cmd: str, timeout: int = 180) -> None:
        print("$", cmd)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out.strip():
            print(out)
        if err.strip():
            print(err)

    run(f"cd {REMOTE} && .venv/bin/python {remote_py}")
    run("systemctl restart qooq-api qooq-admin")
    run("systemctl is-active qooq-api qooq-admin")

    # Probe a live subscription feed if possible
    run(
        f"cd {REMOTE} && .venv/bin/python - <<'PY'\n"
        "import asyncio, base64\n"
        "from sqlalchemy import select\n"
        "from src.db.session import async_session_factory\n"
        "from src.models import Subscription\n"
        "from src.core.enums import SubscriptionStatus\n"
        "from src.core.config import get_settings\n"
        "from src.core.utils import utcnow\n"
        "from src.services.config_credentials import ConfigCredentialService\n"
        "from src.services.vpn_config import build_credential_share_link\n"
        "from src.api.routes.sub_feed import _credential_remark\n\n"
        "async def main():\n"
        "    settings = get_settings()\n"
        "    async with async_session_factory() as session:\n"
        "        sub = (await session.execute(\n"
        "            select(Subscription).where(\n"
        "                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),\n"
        "                Subscription.expires_at > utcnow(),\n"
        "            ).order_by(Subscription.id.desc()).limit(1)\n"
        "        )).scalar_one_or_none()\n"
        "        if not sub:\n"
        "            print('No active subscription to probe'); return\n"
        "        creds, changed = await ConfigCredentialService(session, settings).ensure_credentials(sub)\n"
        "        await session.commit()\n"
        "        active = await ConfigCredentialService(session, settings).list_active(sub.id)\n"
        "        print('sub', sub.id, 'creds', len(active), 'changed', changed)\n"
        "        for c in active:\n"
        "            if not c.vpn_config: continue\n"
        "            link = build_credential_share_link(c.client_uuid, c.vpn_config.config_type.value, c.vpn_config.config_template, _credential_remark(c))\n"
        "            print('-', c.vpn_config.name, '->', link.split('#')[-1] if '#' in link else link[:60], '|', link.split('://')[0])\n"
        "asyncio.run(main())\n"
        "PY"
    )

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
