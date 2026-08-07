"""Referral balance bonuses on referred user deposits."""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import TransactionType
from src.models import ReferralReward, Transaction, User
from src.services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.system_settings = SystemSettingsService(session, settings)

    async def count_referrals(self, user_id: int) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(User).where(User.referred_by_id == user_id)
        )
        return result or 0

    async def total_bonus_earned(self, user_id: int) -> Decimal:
        result = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.REFERRAL_BONUS,
            )
        )
        return Decimal(result or 0).quantize(Decimal("0.01"))

    async def process_deposit_bonus(
        self,
        referred_user: User,
        deposit_amount: Decimal,
        deposit_transaction_id: int,
    ) -> Decimal | None:
        if not referred_user.referred_by_id:
            return None

        existing = await self.session.scalar(
            select(ReferralReward.id).where(
                ReferralReward.source_transaction_id == deposit_transaction_id
            )
        )
        if existing:
            return None

        percent = await self.system_settings.get_referral_bonus_percent()
        if percent <= 0:
            return None

        bonus = (deposit_amount * Decimal(percent) / Decimal(100)).quantize(Decimal("0.01"))
        if bonus <= 0:
            return None

        referrer = await self.session.get(User, referred_user.referred_by_id)
        if not referrer:
            return None

        from src.services import BalanceService

        referred_label = referred_user.first_name or referred_user.username or referred_user.id
        bonus_tx = await BalanceService(self.session).add_balance(
            user_id=referrer.id,
            amount=bonus,
            description=(
                f"Реферальный бонус {percent}% с пополнения "
                f"пользователя {referred_label} (#{referred_user.id})"
            ),
            tx_type=TransactionType.REFERRAL_BONUS,
        )

        reward = ReferralReward(
            referrer_id=referrer.id,
            referred_id=referred_user.id,
            bonus_amount=bonus,
            bonus_days=0,
            is_paid=True,
            source_transaction_id=deposit_transaction_id,
        )
        self.session.add(reward)
        await self.session.flush()

        if self.settings.bot_token:
            await self._notify_referrer(
                telegram_id=referrer.telegram_id,
                bonus=bonus,
                balance=bonus_tx.balance_after,
                percent=percent,
                deposit_amount=deposit_amount,
            )

        logger.info(
            "Referral bonus %s RUB to user %s from deposit tx %s",
            bonus,
            referrer.id,
            deposit_transaction_id,
        )
        return bonus

    async def _notify_referrer(
        self,
        telegram_id: int,
        bonus: Decimal,
        balance: Decimal,
        percent: int,
        deposit_amount: Decimal,
    ) -> None:
        text = (
            f"🎁 <b>Реферальный бонус!</b>\n\n"
            f"Ваш друг пополнил баланс на <b>{deposit_amount} ₽</b>\n"
            f"Вам начислено <b>{percent}%</b>: <b>+{bonus} ₽</b>\n\n"
            f"💳 Баланс: <b>{balance} ₽</b>"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.settings.bot_token}/sendMessage",
                    json={
                        "chat_id": telegram_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
        except Exception:
            logger.exception("Failed to notify referrer %s about bonus", telegram_id)
