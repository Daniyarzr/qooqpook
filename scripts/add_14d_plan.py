"""Create 14-day plan and notify qooqvpnsupport with active sub link."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE_PY = r'''
import asyncio
from decimal import Decimal
from sqlalchemy import select
from src.db.session import async_session_factory
from src.models import SubscriptionPlan, User, Subscription
from src.core.config import get_settings
from src.core.utils import build_subscription_url, format_datetime_ru
from src.services.notifications import send_telegram_message

async def main():
    settings = get_settings()
    async with async_session_factory() as s:
        plan = (await s.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.days == 14, SubscriptionPlan.is_active.is_(True))
        )).scalar_one_or_none()
        if not plan:
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
            print("plan_created", plan.id)
        else:
            print("plan_exists", plan.id)

        user = (await s.execute(select(User).where(User.username == "qooqvpnsupport"))).scalar_one()
        sub = (await s.execute(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.id.desc()).limit(1)
        )).scalar_one_or_none()
        if not sub:
            print("NO_SUB")
        else:
            url = build_subscription_url(settings.hub_domain, sub.subscription_token)
            text = (
                "Подписка активна\n\n"
                f"До: {format_datetime_ru(sub.expires_at)}\n"
                f"Ссылка:\n<code>{url}</code>\n\n"
                "Покупка с баланса исправлена — больше не откатывается."
            )
            ok = await send_telegram_message(settings, user.telegram_id, text)
            print("notified", ok, "sub", sub.id, url)

        plans = (await s.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.sort_order)
        )).scalars().all()
        for p in plans:
            print(f"PLAN {p.sort_order}: {p.name} {p.days}d {p.price}")
        await s.commit()

asyncio.run(main())
'''


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    with sftp.file("/tmp/add_14d_plan.py", "w") as f:
        f.write(REMOTE_PY)
    sftp.close()
    _, o, e = client.exec_command(
        "cd /opt/qooq-vpn && .venv/bin/python /tmp/add_14d_plan.py", timeout=90
    )
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err[-2000:])
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
