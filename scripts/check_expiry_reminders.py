"""Check expiry reminder cron status and recent log."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)

    def run(cmd: str) -> str:
        _, o, e = client.exec_command(cmd, timeout=60)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    print("=== CRON ===")
    print(run("cat /etc/cron.d/qooq-vpn"))
    print("=== LOG TAIL ===")
    print(run("tail -n 30 /var/log/qooq-expiry-reminders.log 2>/dev/null || echo NO_LOG"))
    print("=== DB WINDOW ===")
    print(
        run(
            r"""
cd /opt/qooq-vpn && .venv/bin/python - <<'PY'
import asyncio
from datetime import timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.db.session import async_session_factory
from src.models import Subscription
from src.core.enums import SubscriptionStatus
from src.core.utils import utcnow
from src.services.expiry_reminders import days_until_expiry

MSK = ZoneInfo("Europe/Moscow")

async def main():
    today = utcnow().astimezone(MSK).date()
    async with async_session_factory() as s:
        rows = (await s.execute(
            select(Subscription).options(selectinload(Subscription.user)).where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                Subscription.expires_at > utcnow(),
            )
        )).scalars().all()
        buckets = {1: [], 2: [], 3: [], "other": 0}
        for sub in rows:
            d = days_until_expiry(sub.expires_at, today=today)
            u = sub.user
            label = (u.first_name or u.username or str(u.telegram_id)) if u else "?"
            if d in (1, 2, 3):
                buckets[d].append(f"sub#{sub.id} {label} rem={sub.expiry_reminder_sent} exp={sub.expires_at.astimezone(MSK):%d.%m %H:%M}")
            else:
                buckets["other"] += 1
        for d in (3, 2, 1):
            print(f"--- {d} day(s): {len(buckets[d])} ---")
            for line in buckets[d]:
                print(line)
        print(f"other active: {buckets['other']}")

asyncio.run(main())
PY
"""
        )
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
