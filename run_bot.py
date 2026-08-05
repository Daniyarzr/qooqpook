"""Entry point: Telegram bot."""

import asyncio
import logging

from src.bot.app import run_bot

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    asyncio.run(run_bot())
