"""Fix balance-purchase rollback + add 14-day plan + notify support test account."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/services/__init__.py",
    "src/bot/handlers/subscription.py",
    "src/services/xray_sync.py",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
        print("uploaded", rel)
    sftp.close()

    def run(cmd: str, t: int = 120) -> str:
        _, o, e = client.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode("utf-8", errors="replace")

    print(
        run(
            f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio
from decimal import Decimal
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import SubscriptionPlan, User, Subscription
from src.core.config import get_settings
from src.core.utils import build_subscription_url, format_datetime_ru
from src.services.notifications import send_telegram_message
from src.services import SubscriptionService

async def main():
    settings = get_settings()
    async with async_session_factory() as s:
        existing = (await s.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.days == 14,
                SubscriptionPlan.is_active.is_(True),
            )
        )).scalar_one_or_none()
        if existing:
            print('plan_exists', existing.id, existing.name, existing.price)
            plan = existing
        else:
            # 30д=135 → 14д ≈ 63, ставим 69 ₽
            plan = SubscriptionPlan(
                name="2 недели",
                description="Короткий тариф для теста и старта",
                days=14,
                price=Decimal("69.00"),
                is_active=True,
                sort_order=0,
            )
            s.add(plan)
            await s.flush()
            print('plan_created', plan.id, plan.name, plan.price)

        user = (await s.execute(select(User).where(User.username == 'qooqvpnsupport'))).scalar_one()
        sub = (await s.execute(
            select(Subscription).where(Subscription.user_id == user.id)
            .order_by(Subscription.id.desc()).limit(1)
        )).scalar_one_or_none()
        if sub:
            # ensure credentials + soft link
            await SubscriptionService(s, settings).sync_xray_clients()
            url = build_subscription_url(settings.hub_domain, sub.subscription_token)
            text = (
                "✅ <b>Подписка активна</b>\n\n"
                f"📅 До: <b>{{format_datetime_ru(sub.expires_at)}}</b>\n"
                f"🔗 Ссылка:\n<code>{{url}}</code>\n\n"
                "Ранее покупка с баланса могла откатываться из‑за таймаута "
                "синхронизации VPN — это исправлено."
            )
            ok = await send_telegram_message(settings, user.telegram_id, text)
            print('notified', ok, 'sub', sub.id, url)
        else:
            print('NO_SUB_FOR_SUPPORT')
        await s.commit()

asyncio.run(main())
PY
"""
        )
    )
    print(run("systemctl restart qooq-bot qooq-api"))
    time.sleep(6)
    print("STATUS", run("systemctl is-active qooq-bot qooq-api"))
    print(
        run(
            f"""
cd {REMOTE} && .venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import SubscriptionPlan
async def main():
    async with async_session_factory() as s:
        plans = (await s.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_active==True)
            .order_by(SubscriptionPlan.sort_order)
        )).scalars().all()
        for p in plans:
            print(f'{{p.sort_order}}: {{p.name}} — {{p.days}}д / {{p.price}}₽')
asyncio.run(main())
PY
"""
        )
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
