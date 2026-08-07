from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import SubscriptionPlan
from src.services.promo import PromoCodeService, PromoValidation


@dataclass
class PurchasePricing:
    original_price: Decimal
    final_price: Decimal
    discount_amount: Decimal
    promo: PromoValidation | None
    description_suffix: str


class PurchasePricingService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.promo_service = PromoCodeService(session)

    async def resolve(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        promo_code_id: int | None = None,
    ) -> PurchasePricing:
        original = plan.price
        promo = None
        if promo_code_id:
            promo = await self.promo_service.validate_by_id(promo_code_id, user_id, plan)

        if promo:
            return PurchasePricing(
                original_price=original,
                final_price=promo.final_price,
                discount_amount=promo.discount_amount,
                promo=promo,
                description_suffix=f" (промокод {promo.promo.code}, −{promo.discount_amount} ₽)",
            )

        return PurchasePricing(
            original_price=original,
            final_price=original,
            discount_amount=Decimal("0.00"),
            promo=None,
            description_suffix="",
        )
