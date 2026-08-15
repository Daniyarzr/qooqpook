import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import TelegramAdmin

logger = logging.getLogger(__name__)


async def send_telegram_message(settings: Settings, telegram_id: int, text: str) -> bool:
    if not settings.bot_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            return response.status_code == 200
    except Exception:
        logger.exception("Failed to send Telegram message to %s", telegram_id)
        return False


async def list_active_telegram_admin_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(TelegramAdmin.telegram_id).where(TelegramAdmin.is_active.is_(True))
    )
    return list(result.scalars().all())


async def is_telegram_admin(session: AsyncSession, telegram_id: int, settings: Settings) -> bool:
    result = await session.execute(
        select(TelegramAdmin.id).where(
            TelegramAdmin.telegram_id == telegram_id,
            TelegramAdmin.is_active.is_(True),
        )
    )
    if result.scalar_one_or_none() is not None:
        return True
    return telegram_id in (settings.admin_telegram_ids or [])


async def notify_telegram_admins(
    session: AsyncSession,
    settings: Settings,
    text: str,
) -> None:
    """Шлёт сообщение всем активным Telegram-админам из админ-панели."""
    admin_ids = await list_active_telegram_admin_ids(session)
    # Fallback на .env, если в БД ещё никого не добавили
    if not admin_ids and settings.admin_telegram_ids:
        admin_ids = list(settings.admin_telegram_ids)

    # Без дублей (один и тот же id в таблице / env)
    seen: set[int] = set()
    for telegram_id in admin_ids:
        if telegram_id in seen:
            continue
        seen.add(telegram_id)
        ok = await send_telegram_message(settings, telegram_id, text)
        if not ok:
            logger.warning("Admin payment notify failed for telegram_id=%s", telegram_id)
