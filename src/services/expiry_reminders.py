"""Daily Telegram reminders: subscription ends in 3 / 2 / 1 day(s)."""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.config import Settings
from src.core.enums import SubscriptionStatus
from src.core.utils import format_datetime_ru, utcnow
from src.models import Subscription, User
from src.services.notifications import send_telegram_message

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
REMINDER_DAYS = (3, 2, 1)


@dataclass(frozen=True)
class ReminderTemplate:
    days: int
    emoji: str
    title: str
    lead: str
    urgency: str


TEMPLATES: dict[int, ReminderTemplate] = {
    3: ReminderTemplate(
        days=3,
        emoji="⏳",
        title="Подписка заканчивается через 3 дня",
        lead="Ещё есть время спокойно продлить доступ — без спешки и паузы в работе.",
        urgency="Через <b>3 дня</b> VPN перестанет подключаться, пока не продлите тариф.",
    ),
    2: ReminderTemplate(
        days=2,
        emoji="⚠️",
        title="Подписка заканчивается через 2 дня",
        lead="До отключения осталось совсем немного — лучше продлить сегодня.",
        urgency="Через <b>2 дня</b> доступ к QooQ VPN будет приостановлен.",
    ),
    1: ReminderTemplate(
        days=1,
        emoji="🚨",
        title="Подписка заканчивается завтра",
        lead="Это последнее напоминание перед отключением.",
        urgency="Уже <b>завтра</b> подписка истечёт — продлите сейчас, чтобы не потерять связь.",
    ),
}


def days_until_expiry(expires_at: datetime, *, today: date | None = None) -> int:
    """Calendar days left until expiry date in Europe/Moscow."""
    local_today = today or utcnow().astimezone(MSK).date()
    exp_date = expires_at.astimezone(MSK).date()
    return (exp_date - local_today).days


def user_display_name(user: User) -> str | None:
    name = (user.first_name or "").strip()
    if name:
        return name
    username = (user.username or "").strip().lstrip("@")
    return username or None


def build_expiry_reminder_text(
    *,
    days: int,
    expires_at: datetime,
    first_name: str | None = None,
) -> str:
    tpl = TEMPLATES[days]
    name = (first_name or "").strip()
    greeting = f"Привет, <b>{html.escape(name)}</b>!" if name else "Привет!"
    when = format_datetime_ru(expires_at)
    day_word = {3: "3 дня", 2: "2 дня", 1: "1 день"}[days]
    return (
        f"{tpl.emoji} <b>{tpl.title}</b>\n"
        f"{'─' * 18}\n\n"
        f"{greeting}\n\n"
        f"{tpl.lead}\n\n"
        f"📅 Активна до: <b>{when}</b> (МСК)\n"
        f"⏱ Осталось: <b>{day_word}</b>\n\n"
        f"{tpl.urgency}\n\n"
        f"Нажмите <b>«Продлить»</b> ниже — тарифы откроются в боте 💎"
    )


def renew_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="sub:plans")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile")],
        ]
    )


class ExpiryReminderService:
    def __init__(self, session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def list_active_with_users(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                )
            )
            .where(Subscription.expires_at > utcnow())
        )
        return list(result.scalars().all())

    async def process_due_reminders(self) -> dict[str, int]:
        stats = {"checked": 0, "sent": 0, "skipped": 0, "failed": 0}
        today = utcnow().astimezone(MSK).date()
        for sub in await self.list_active_with_users():
            stats["checked"] += 1
            user = sub.user
            if not user or not user.telegram_id or user.is_banned:
                stats["skipped"] += 1
                continue
            days = days_until_expiry(sub.expires_at, today=today)
            if days not in REMINDER_DAYS:
                stats["skipped"] += 1
                continue
            already = sub.expiry_reminder_sent
            if already is not None and already <= days:
                stats["skipped"] += 1
                continue
            ok = await self._send(user, sub, days)
            if ok:
                sub.expiry_reminder_sent = days
                stats["sent"] += 1
                await self.session.flush()
            else:
                stats["failed"] += 1
            await asyncio.sleep(0.05)
        return stats

    async def _send(self, user: User, sub: Subscription, days: int) -> bool:
        text = build_expiry_reminder_text(
            days=days,
            expires_at=sub.expires_at,
            first_name=user_display_name(user),
        )
        return await send_telegram_message(
            self.settings,
            user.telegram_id,
            text,
            reply_markup=renew_keyboard(),
        )
