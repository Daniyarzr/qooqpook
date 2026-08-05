from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.enums import PromoDiscountType
from src.core.utils import utcnow
from src.models import PromoCode, PromoCodeRedemption, SubscriptionPlan


@dataclass
class PromoValidation:
    promo: PromoCode
    original_price: Decimal
    discount_amount: Decimal
    final_price: Decimal


class PromoCodeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> PromoCode | None:
        normalized = code.strip().upper()
        result = await self.session.execute(
            select(PromoCode)
            .options(selectinload(PromoCode.plan))
            .where(PromoCode.code == normalized)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, promo_id: int) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode)
            .options(selectinload(PromoCode.plan))
            .where(PromoCode.id == promo_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PromoCode]:
        result = await self.session.execute(
            select(PromoCode)
            .options(selectinload(PromoCode.plan))
            .order_by(PromoCode.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, promo: PromoCode) -> PromoCode:
        self.session.add(promo)
        await self.session.flush()
        return promo

    async def count_user_redemptions(self, promo_id: int, user_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(PromoCodeRedemption)
            .where(
                PromoCodeRedemption.promo_code_id == promo_id,
                PromoCodeRedemption.user_id == user_id,
            )
        )
        return result or 0


class PromoCodeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PromoCodeRepository(session)

    @staticmethod
    def normalize_code(code: str) -> str:
        return code.strip().upper()

    @staticmethod
    def calculate_discount(plan: SubscriptionPlan, promo: PromoCode) -> tuple[Decimal, Decimal]:
        original = plan.price
        if promo.discount_type == PromoDiscountType.PERCENT:
            discount = (original * promo.discount_value / Decimal(100)).quantize(Decimal("0.01"))
        else:
            discount = min(promo.discount_value, original)
        final_price = max(Decimal("0.00"), original - discount)
        return discount, final_price

    async def validate(self, code: str, user_id: int, plan: SubscriptionPlan) -> PromoValidation:
        promo = await self.repo.get_by_code(code)
        if not promo:
            raise ValueError("Промокод не найден")
        if not promo.is_active:
            raise ValueError("Промокод деактивирован")

        now = utcnow()
        if promo.valid_from and now < promo.valid_from:
            raise ValueError("Промокод ещё не активен")
        if promo.valid_until and now > promo.valid_until:
            raise ValueError("Срок действия промокода истёк")
        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            raise ValueError("Промокод исчерпан")
        if promo.plan_id and promo.plan_id != plan.id:
            raise ValueError("Промокод не подходит для выбранного тарифа")

        user_uses = await self.repo.count_user_redemptions(promo.id, user_id)
        if user_uses >= promo.max_uses_per_user:
            raise ValueError("Вы уже использовали этот промокод")

        discount, final_price = self.calculate_discount(plan, promo)
        if final_price <= 0 and discount <= 0:
            raise ValueError("Промокод не даёт скидку для этого тарифа")

        return PromoValidation(
            promo=promo,
            original_price=plan.price,
            discount_amount=discount,
            final_price=final_price,
        )

    async def validate_by_id(self, promo_id: int, user_id: int, plan: SubscriptionPlan) -> PromoValidation:
        promo = await self.repo.get_by_id(promo_id)
        if not promo:
            raise ValueError("Промокод не найден")
        return await self.validate(promo.code, user_id, plan)

    async def redeem(
        self,
        promo: PromoCode,
        user_id: int,
        subscription_id: int | None,
        validation: PromoValidation,
    ) -> PromoCodeRedemption:
        promo.used_count += 1
        redemption = PromoCodeRedemption(
            promo_code_id=promo.id,
            user_id=user_id,
            subscription_id=subscription_id,
            original_price=validation.original_price,
            discount_amount=validation.discount_amount,
            final_price=validation.final_price,
        )
        self.session.add(redemption)
        await self.session.flush()
        return redemption

    async def create_promo(
        self,
        code: str,
        discount_type: PromoDiscountType,
        discount_value: Decimal,
        description: str | None = None,
        plan_id: int | None = None,
        max_uses: int | None = None,
        max_uses_per_user: int = 1,
        valid_until=None,
    ) -> PromoCode:
        normalized = self.normalize_code(code)
        existing = await self.repo.get_by_code(normalized)
        if existing:
            raise ValueError("Промокод с таким кодом уже существует")
        if discount_value <= 0:
            raise ValueError("Размер скидки должен быть больше 0")
        if discount_type == PromoDiscountType.PERCENT and discount_value > 100:
            raise ValueError("Процент скидки не может быть больше 100")

        promo = PromoCode(
            code=normalized,
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            plan_id=plan_id,
            max_uses=max_uses,
            max_uses_per_user=max_uses_per_user,
            valid_until=valid_until,
        )
        return await self.repo.create(promo)

    async def toggle_active(self, promo_id: int) -> PromoCode | None:
        promo = await self.repo.get_by_id(promo_id)
        if not promo:
            return None
        promo.is_active = not promo.is_active
        await self.session.flush()
        return promo

    async def delete_promo(self, promo_id: int) -> bool:
        promo = await self.repo.get_by_id(promo_id)
        if not promo:
            return False
        if promo.used_count > 0:
            raise ValueError("Нельзя удалить промокод с историей использования")
        await self.session.delete(promo)
        await self.session.flush()
        return True
