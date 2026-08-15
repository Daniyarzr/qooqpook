import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.commands import setup_bot_commands
from src.bot.handlers import (
    broadcast,
    devices,
    direct_message,
    payment,
    profile,
    reply_menu,
    start,
    subscription,
)
from src.bot.middlewares.db import DbSessionMiddleware
from src.bot.middlewares.settings import SettingsMiddleware
from src.core.config import get_settings

logger = logging.getLogger(__name__)


def create_bot() -> tuple[Bot, Dispatcher]:
    settings = get_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(SettingsMiddleware(settings))
    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(start.router)
    dp.include_router(reply_menu.router)
    dp.include_router(broadcast.router)
    dp.include_router(direct_message.router)
    dp.include_router(subscription.router)
    dp.include_router(profile.router)
    dp.include_router(payment.router)
    dp.include_router(devices.router)

    return bot, dp


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set in .env")

    bot, dp = create_bot()
    await setup_bot_commands(bot)
    logger.info("Starting QooQ VPN bot...")
    await dp.start_polling(bot)
