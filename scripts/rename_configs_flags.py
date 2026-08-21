"""Add country flag emojis to plain config names."""
from __future__ import annotations

import json
import os
import sys

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]

RENAMES = {
    10: "🇷🇺 Основной",
    12: "🇫🇮 Финляндия (QooQ)",
    13: "🇺🇸 США",
    14: "🇩🇪 Германия",
    15: "🇦🇹 Австрия",
    16: "🇸🇪 Швеция",
    17: "🇸🇪 Швеция 2",
    18: "🇫🇮 Финляндия",
    19: "🇳🇱 Нидерланды",
    20: "🇷🇺 Россия LTE",
    21: "🇸🇪 Швеция LTE",
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    payload = json.dumps(RENAMES, ensure_ascii=False)
    sftp = client.open_sftp()
    with sftp.file("/opt/qooq-vpn/_rename_configs.json", "w") as fh:
        fh.write(payload)
    with sftp.file("/opt/qooq-vpn/_rename_configs.py", "w") as fh:
        fh.write(
            r'''
import asyncio, json
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import VpnConfig

RENAMES = {int(k): v for k, v in json.load(open("/opt/qooq-vpn/_rename_configs.json", encoding="utf-8")).items()}

async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(VpnConfig).where(VpnConfig.id.in_(list(RENAMES))))
        for cfg in result.scalars().all():
            old, new = cfg.name, RENAMES[cfg.id]
            cfg.name = new
            try:
                data = json.loads(cfg.config_template)
                if isinstance(data, dict) and "remarks" in data:
                    data["remarks"] = new
                    cfg.config_template = json.dumps(data, ensure_ascii=False, indent=2)
            except Exception:
                pass
            print(f"{cfg.id}: {old!r} -> {new!r}")
        await session.commit()

asyncio.run(main())
'''
        )
    sftp.close()

    def run(cmd: str, timeout: int = 60) -> None:
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        print(stdout.read().decode("utf-8", errors="replace"))
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            print(err)

    run("cd /opt/qooq-vpn && .venv/bin/python /opt/qooq-vpn/_rename_configs.py")
    run(
        r'''curl -sS "http://127.0.0.1:8000/sub/RllTXDPQO2uRRkV46WWVyb56TGwK4cX3YTur2D5pEYc" | python3 -c "
import sys, base64, urllib.parse
raw=sys.stdin.buffer.read().strip()
body=base64.b64decode(raw).decode()
for l in body.splitlines():
  if l.strip():
    print('-', urllib.parse.unquote(l.rsplit('#',1)[-1]))
"'''
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
