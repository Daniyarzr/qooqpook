from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import SubscriptionPlan
from src.services.promo import PromoCodeService, PromoValidation
from src.services.referral import ReferralDiscount, ReferralService


@dataclass
class PurchasePricing:
    original_price: Decimal
    final_price: Decimal
    discount_amount: Decimal
    referral: ReferralDiscount | None
    promo: PromoValidation | None
    description_suffix: str


class PurchasePricingService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.referral_service = ReferralService(session, settings)
        self.promo_service = PromoCodeService(session)

    async def resolve(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        promo_code_id: int | None = None,
    ) -> PurchasePricing:
        original = plan.price
        referral = await self.referral_service.calculate(user_id, plan)
        promo = None
        if promo_code_id:
            promo = await self.promo_service.validate_by_id(promo_code_id, user_id, plan)

        referral_price = referral.final_price if referral else original
        promo_price = promo.final_price if promo else original
        final_price = min(referral_price, promo_price)

        if promo and promo_price <= referral_price:
            chosen_referral = None
            chosen_promo = promo
            discount_amount = promo.discount_amount
            suffix = f" (промокод {promo.promo.code}, −{promo.discount_amount} ₽)"
        elif referral:
            chosen_referral = referral
            chosen_promo = None
            discount_amount = referral.discount_amount
            suffix = f" ({referral.label}, −{referral.discount_amount} ₽)"
        else:
            chosen_referral = None
            chosen_promo = None
            discount_amount = Decimal("0.00")
            suffix = ""

        return PurchasePricing(
            original_price=original,
            final_price=final_price,
            discount_amount=discount_amount,
            referral=chosen_referral,
            promo=chosen_promo,
            description_suffix=suffix,
        )
