"""Ensure config credentials exist for all active subscriptions."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.core.config import get_settings
from src.core.enums import SubscriptionStatus
from src.db.session import async_session_factory
from src.models import Subscription
from src.services import SubscriptionService
from src.services.config_credentials import ConfigCredentialService


async def main() -> int:
    settings = get_settings()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        subscriptions = list(result.scalars().all())
        cred_service = ConfigCredentialService(session, settings)
        for subscription in subscriptions:
            await cred_service.ensure_credentials(subscription)
        await session.commit()
        await SubscriptionService(session, settings).sync_xray_clients()
        print(f"Ensured credentials for {len(subscriptions)} subscriptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
