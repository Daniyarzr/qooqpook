"""Poll pending YooKassa orders and fulfill succeeded ones (webhook safety net)."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.db.session import async_session_factory
from src.services.payment import PaymentService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    settings = get_settings()
    if not settings.yookassa_enabled:
        logger.info("YooKassa disabled — skip")
        return 0

    async with async_session_factory() as session:
        service = PaymentService(session, settings)
        fulfilled = await service.poll_pending_orders()
        await session.commit()
        if fulfilled:
            logger.info("Fulfilled %s pending YooKassa order(s)", fulfilled)
        else:
            logger.info("No pending YooKassa orders to fulfill")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
