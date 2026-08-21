"""Notify users whose subscription ends in 3 / 2 / 1 day(s). Cron daily."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.db.session import async_session_factory
from src.services.expiry_reminders import ExpiryReminderService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main_async() -> int:
    settings = get_settings()
    async with async_session_factory() as session:
        stats = await ExpiryReminderService(session, settings).process_due_reminders()
        await session.commit()
    logger.info(
        "Expiry reminders: checked=%s sent=%s skipped=%s failed=%s",
        stats["checked"],
        stats["sent"],
        stats["skipped"],
        stats["failed"],
    )
    return 0 if stats["failed"] == 0 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
