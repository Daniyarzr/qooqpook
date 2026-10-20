"""Notify users whose subscription ends in 3 / 2 / 1 day(s). Cron daily."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.db.session import async_session_factory
from src.services.expiry_reminders import ExpiryReminderService, PurchaseNudgeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main_async() -> int:
    settings = get_settings()
    async with async_session_factory() as session:
        expiry = await ExpiryReminderService(session, settings).process_due_reminders()
        nudges = await PurchaseNudgeService(session, settings).process_due_nudges()
        await session.commit()
    logger.info(
        "Expiry reminders: checked=%s sent=%s skipped=%s failed=%s",
        expiry["checked"],
        expiry["sent"],
        expiry["skipped"],
        expiry["failed"],
    )
    logger.info(
        "Purchase nudges: checked=%s sent=%s failed=%s",
        nudges["checked"],
        nudges["sent"],
        nudges["failed"],
    )
    return 0 if expiry["failed"] == 0 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
