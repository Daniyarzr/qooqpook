"""Fix sub 500: deploy ManualVpnKey model + ensure migration."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/models/__init__.py",
    "src/services/__init__.py",
    "alembic/versions/014_manual_vpn_keys.py",
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

    def run(cmd: str, timeout: int = 120) -> None:
        print("$", cmd)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out.strip():
            print(out)
        if err.strip():
            print(err)

    run(f"cd {REMOTE} && .venv/bin/alembic upgrade head")
    run(
        f"cd {REMOTE} && .venv/bin/python -c "
        "\"from src.models import ManualVpnKey; print('ManualVpnKey OK', ManualVpnKey.__tablename__)\""
    )
    run("systemctl restart qooq-api qooq-admin qooq-bot")
    run("systemctl is-active qooq-api qooq-admin qooq-bot")
    run(
        "TOKEN=$(cd /opt/qooq-vpn && .venv/bin/python - <<'PY'\n"
        "import asyncio\n"
        "from sqlalchemy import select\n"
        "from src.db.session import async_session_factory\n"
        "from src.models import Subscription\n"
        "from src.core.enums import SubscriptionStatus\n"
        "from src.core.utils import utcnow\n"
        "async def main():\n"
        "  async with async_session_factory() as s:\n"
        "    sub=(await s.execute(select(Subscription).where(Subscription.status.in_([SubscriptionStatus.ACTIVE,SubscriptionStatus.TRIAL]), Subscription.expires_at>utcnow()).order_by(Subscription.id.desc()).limit(1))).scalar_one_or_none()\n"
        "    print(sub.subscription_token if sub else '')\n"
        "asyncio.run(main())\n"
        "PY\n"
        "); echo TOKEN=$TOKEN; curl -sS -o /tmp/sub_out.txt -w 'HTTP %{http_code} bytes %{size_download}\\n' \"http://127.0.0.1:8000/sub/$TOKEN\"; "
        "python3 - <<'PY'\n"
        "import base64\n"
        "raw=open('/tmp/sub_out.txt','rb').read().strip()\n"
        "try:\n"
        "  body=base64.b64decode(raw).decode('utf-8','replace')\n"
        "except Exception:\n"
        "  body=raw.decode('utf-8','replace')\n"
        "lines=[l for l in body.splitlines() if l.strip()]\n"
        "print('lines', len(lines))\n"
        "for l in lines[:15]:\n"
        "  print('-', l.split('://')[0], '#', l.rsplit('#',1)[-1][:80] if '#' in l else l[:60])\n"
        "PY"
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
