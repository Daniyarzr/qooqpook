import asyncio
import logging
from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import TelegramAdmin

logger = logging.getLogger(__name__)


async def _telegram_api(settings: Settings, method: str, payload: dict[str, Any]) -> bool:
    if not settings.bot_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/{method}",
                json=payload,
            )
            if response.status_code != 200:
                logger.warning("Telegram %s failed: %s", method, response.text[:200])
            return response.status_code == 200
    except Exception:
        logger.exception("Telegram API call failed: %s", method)
        return False


async def send_telegram_message(
    settings: Settings,
    telegram_id: int,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | dict | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        if hasattr(reply_markup, "model_dump"):
            payload["reply_markup"] = reply_markup.model_dump(exclude_none=True)
        else:
            payload["reply_markup"] = reply_markup
    return await _telegram_api(settings, "sendMessage", payload)


async def list_active_telegram_admin_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(TelegramAdmin.telegram_id).where(TelegramAdmin.is_active.is_(True))
    )
    return list(result.scalars().all())


async def is_telegram_admin(
    session: AsyncSession, telegram_id: int, settings: Settings
) -> bool:
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
    """Send message to all active Telegram admins (panel list, else .env fallback)."""
    admin_ids = await list_active_telegram_admin_ids(session)
    if not admin_ids and settings.admin_telegram_ids:
        admin_ids = list(settings.admin_telegram_ids)

    seen: set[int] = set()
    for telegram_id in admin_ids:
        if telegram_id in seen:
            continue
        seen.add(telegram_id)
        ok = await send_telegram_message(settings, telegram_id, text)
        if not ok:
            logger.warning("Admin notify failed for telegram_id=%s", telegram_id)


async def send_broadcast_payload(
    settings: Settings,
    telegram_id: int,
    payload: dict[str, Any],
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    markup = None
    if reply_markup is not None:
        markup = reply_markup.model_dump(exclude_none=True)

    if payload.get("kind") == "photo":
        data: dict[str, Any] = {
            "chat_id": telegram_id,
            "photo": payload.get("photo_file_id"),
        }
        caption = (payload.get("caption") or "").strip()
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        if markup:
            data["reply_markup"] = markup
        return await _telegram_api(settings, "sendPhoto", data)

    text = (payload.get("text") or "").strip()
    if not text:
        return False
    return await send_telegram_message(settings, telegram_id, text, reply_markup=reply_markup)


async def broadcast_payload_to_all(
    settings: Settings,
    payload: dict[str, Any],
    telegram_ids: list[int],
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0
    for telegram_id in telegram_ids:
        if await send_broadcast_payload(settings, telegram_id, payload, reply_markup=reply_markup):
            ok_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.05)
    return ok_count, fail_count
