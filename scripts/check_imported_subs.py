"""Recheck imported subscription endpoints. Cron every 30 minutes."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.session import async_session_factory
from src.services.imported_subs import refresh_active_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main_async() -> int:
    async with async_session_factory() as session:
        stats = await refresh_active_sources(session)
        await session.commit()
    logger.info("Imported subs: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
