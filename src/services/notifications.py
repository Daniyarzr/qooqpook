import logging

import httpx

from src.core.config import Settings

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
