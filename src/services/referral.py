from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import SubscriptionPlan, User
from src.services.system_settings import SystemSettingsService


@dataclass
class ReferralDiscount:
    original_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    discount_percent: int
    referrals_count: int
    welcome_applied: bool
    label: str


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

    async def calculate(self, user_id: int, plan: SubscriptionPlan) -> ReferralDiscount | None:
        user = await self.session.get(User, user_id)
        if not user:
            return None

        percent_per = await self.system_settings.get_referral_discount_percent()
        if percent_per <= 0:
            return None

        referrals_count = await self.count_referrals(user_id)
        welcome = bool(user.referred_by_id and not user.referral_discount_used)

        total_percent = 0
        if welcome:
            total_percent += percent_per
        if referrals_count:
            total_percent += referrals_count * percent_per
        total_percent = min(100, total_percent)

        if total_percent <= 0:
            return None

        original = plan.price
        discount = (original * Decimal(total_percent) / Decimal(100)).quantize(Decimal("0.01"))
        final_price = max(Decimal("0.00"), original - discount)

        parts = []
        if welcome:
            parts.append(f"скидка по ссылке −{percent_per}%")
        if referrals_count:
            parts.append(f"{referrals_count} реф. × {percent_per}%")
        label = "Реферальная скидка (" + ", ".join(parts) + ")"

        return ReferralDiscount(
            original_price=original,
            discount_amount=discount,
            final_price=final_price,
            discount_percent=total_percent,
            referrals_count=referrals_count,
            welcome_applied=welcome,
            label=label,
        )

    async def mark_welcome_used(self, user: User, discount: ReferralDiscount) -> None:
        if discount.welcome_applied and not user.referral_discount_used:
            user.referral_discount_used = True
            await self.session.flush()
