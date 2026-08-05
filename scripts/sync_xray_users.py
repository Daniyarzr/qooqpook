"""Sync active subscription UUIDs to the Xray VPN node (cron/systemd timer)."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.db.session import async_session_factory
from src.services import SubscriptionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    settings = get_settings()
    async with async_session_factory() as session:
        service = SubscriptionService(session, settings)
        expired = await service.suspend_expired()
        if expired:
            logger.info("Marked %s subscriptions as expired", expired)
        synced = await service.sync_xray_clients()
        if synced:
            logger.info("Xray client list updated")
        elif settings.xray_sync_enabled:
            logger.warning("Xray sync failed or disabled")
        await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
