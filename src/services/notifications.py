import asyncio
import logging
from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup

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
