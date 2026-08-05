"""Sync traffic usage from Xray Stats API (cron)."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.admin.services import AdminService
from src.core.config import get_settings
from src.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    settings = get_settings()
    if not settings.xray_stats_enabled:
        logger.info("Xray stats disabled, skipping traffic sync")
        return 0

    async with async_session_factory() as session:
        service = AdminService(session)
        updated = await service.sync_all_traffic(settings)
        await session.commit()
        logger.info("Traffic synced for %s subscriptions", updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
