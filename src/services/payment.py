import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import (
    PaymentMethod,
    PaymentOrderPurpose,
    PaymentStatus,
    TransactionType,
)
from src.core.utils import build_subscription_url, format_datetime_ru, utcnow
from src.models import PaymentOrder, Transaction
from src.repositories import PaymentOrderRepository, PlanRepository, UserRepository
from src.services import BalanceService
from src.services.notifications import notify_telegram_admins, send_telegram_message
from src.services.yookassa import YooKassaClient, YooKassaError

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.orders = PaymentOrderRepository(session)
        self.users = UserRepository(session)
        self.plans = PlanRepository(session)
        self.balance = BalanceService(session)
        self.yookassa = YooKassaClient(settings)

    async def create_deposit(self, user_id: int, amount: Decimal) -> PaymentOrder:
        if not self.yookassa.enabled:
            raise ValueError("YooKassa is not configured")

        self._validate_amount(amount)

        user = await self.users.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        order = await self.orders.create(
            PaymentOrder(
                user_id=user_id,
                amount=amount,
                external_id=str(uuid.uuid4()),
                status=PaymentStatus.PENDING,
                purpose=PaymentOrderPurpose.DEPOSIT,
            )
        )

        try:
            payment = await self.yookassa.create_payment(
                amount=amount,
                order_id=order.id,
                user_id=user_id,
                description=f"Пополнение баланса QooQ VPN (#{order.id})",
            )
        except YooKassaError as exc:
            order.status = PaymentStatus.CANCELED
            await self.session.flush()
            raise ValueError("Failed to create payment") from exc

        order.external_id = payment["id"]
        order.payment_url = payment["confirmation"]["confirmation_url"]
        await self.session.flush()
        return order

    async def create_purchase(
        self,
        user_id: int,
        plan_id: int,
        promo_code_id: int | None = None,
    ) -> PaymentOrder:
        if not self.yookassa.enabled:
            raise ValueError("YooKassa is not configured")

        user = await self.users.get_by_id(user_id)
        plan = await self.plans.get_by_id(plan_id)
        if not user or not plan or not plan.is_active:
            raise ValueError("User or plan not found")

        from src.services.pricing import PurchasePricingService

        pricing = await PurchasePricingService(self.session, self.settings).resolve(
            user_id, plan, promo_code_id
        )
        amount = pricing.final_price
        self._validate_amount(amount)

        order = await self.orders.create(
            PaymentOrder(
                user_id=user_id,
                amount=amount,
                external_id=str(uuid.uuid4()),
                status=PaymentStatus.PENDING,
                purpose=PaymentOrderPurpose.SUBSCRIPTION,
                plan_id=plan_id,
                promo_code_id=promo_code_id,
            )
        )

        try:
            payment = await self.yookassa.create_payment(
                amount=amount,
                order_id=order.id,
                user_id=user_id,
                description=f"Подписка QooQ VPN: {plan.name} (#{order.id})",
            )
        except YooKassaError as exc:
            order.status = PaymentStatus.CANCELED
            await self.session.flush()
            raise ValueError("Failed to create payment") from exc

        order.external_id = payment["id"]
        order.payment_url = payment["confirmation"]["confirmation_url"]
        await self.session.flush()
        return order

    def _validate_amount(self, amount: Decimal) -> None:
        if amount < Decimal(self.settings.deposit_min_amount):
            raise ValueError(f"Minimum amount is {self.settings.deposit_min_amount} ₽")
        if amount > Decimal(self.settings.deposit_max_amount):
            raise ValueError(f"Maximum amount is {self.settings.deposit_max_amount} ₽")

    async def process_payment_success(self, external_id: str) -> PaymentOrder | None:
        order = await self.orders.get_by_external_id_for_update(external_id)
        if not order:
            logger.warning("Payment order not found for external_id=%s", external_id)
            return None

        if order.status == PaymentStatus.SUCCEEDED:
            if order.purpose == PaymentOrderPurpose.SUBSCRIPTION:
                await self._ensure_subscription_fulfilled(order)
            elif order.purpose == PaymentOrderPurpose.DEPOSIT:
                await self._ensure_deposit_fulfilled(order)
            return order

        try:
            payment = await self.yookassa.get_payment(external_id)
        except YooKassaError:
            logger.exception("YooKassa get_payment failed for %s", external_id)
            return None

        if payment.get("status") != "succeeded":
            return None

        paid_amount = Decimal(payment["amount"]["value"]).quantize(Decimal("0.01"))
        order_amount = Decimal(order.amount).quantize(Decimal("0.01"))
        if paid_amount != order_amount:
            logger.error(
                "Payment amount mismatch: order=%s paid=%s external_id=%s",
                order_amount,
                paid_amount,
                external_id,
            )
            return None

        if order.purpose == PaymentOrderPurpose.SUBSCRIPTION:
            if not await self._fulfill_subscription_order(order):
                return None
        else:
            await self._fulfill_deposit_order(order)

        order.status = PaymentStatus.SUCCEEDED
        order.paid_at = utcnow()
        await self.session.flush()
        # Уведомление админов только при первом переходе PENDING → SUCCEEDED
        await self._notify_admins_about_order(order)
        return order

    async def _notify_admins_about_order(self, order: PaymentOrder) -> None:
        user = await self.users.get_by_id(order.user_id)
        user_label = "—"
        tg_id = "—"
        if user:
            tg_id = str(user.telegram_id)
            parts = [p for p in [user.username and f"@{user.username}", user.first_name] if p]
            user_label = " / ".join(parts) if parts else f"id={user.id}"

        if order.purpose == PaymentOrderPurpose.SUBSCRIPTION:
            plan = await self.plans.get_by_id(order.plan_id) if order.plan_id else None
            plan_name = plan.name if plan else f"plan#{order.plan_id}"
            text = (
                "💳 <b>Новый платёж — подписка</b>\n\n"
                f"👤 {user_label}\n"
                f"🆔 Telegram ID: <code>{tg_id}</code>\n"
                f"💎 Тариф: <b>{plan_name}</b>\n"
                f"💰 Сумма: <b>{order.amount} ₽</b>\n"
                f"🧾 Заказ: <code>#{order.id}</code>\n"
                f"🏦 ЮKassa: <code>{order.external_id}</code>"
            )
        else:
            text = (
                "💳 <b>Новый платёж — пополнение</b>\n\n"
                f"👤 {user_label}\n"
                f"🆔 Telegram ID: <code>{tg_id}</code>\n"
                f"💰 Сумма: <b>{order.amount} ₽</b>\n"
                f"🧾 Заказ: <code>#{order.id}</code>\n"
                f"🏦 ЮKassa: <code>{order.external_id}</code>"
            )
        await notify_telegram_admins(self.session, self.settings, text)

    async def _ensure_subscription_fulfilled(self, order: PaymentOrder) -> None:
        if await self._is_subscription_fulfilled(order):
            return
        await self._fulfill_subscription_order(order)

    async def _ensure_deposit_fulfilled(self, order: PaymentOrder) -> None:
        if await self._is_deposit_fulfilled(order):
            return
        await self._fulfill_deposit_order(order, notify_user=False)

    async def _is_subscription_fulfilled(self, order: PaymentOrder) -> bool:
        marker = f"(#{order.id})"
        result = await self.session.execute(
            select(Transaction.id)
            .where(
                Transaction.user_id == order.user_id,
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT,
                Transaction.description.like(f"%{marker}%"),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _is_deposit_fulfilled(self, order: PaymentOrder) -> bool:
        marker = f"(#{order.id})"
        result = await self.session.execute(
            select(Transaction.id)
            .where(
                Transaction.user_id == order.user_id,
                Transaction.type == TransactionType.DEPOSIT,
                Transaction.description.like(f"%{marker}%"),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _fulfill_deposit_order(
        self,
        order: PaymentOrder,
        *,
        notify_user: bool = True,
    ) -> PaymentOrder:
        if await self._is_deposit_fulfilled(order):
            return order

        tx = await self.balance.add_balance(
            user_id=order.user_id,
            amount=order.amount,
            description=f"Пополнение через ЮKassa (#{order.id})",
            payment_method=PaymentMethod.YOOKASSA,
        )

        user = await self.users.get_by_id(order.user_id)
        if user:
            from src.services.referral import ReferralService

            await ReferralService(self.session, self.settings).process_deposit_bonus(
                user,
                order.amount,
                tx.id,
            )

        if notify_user and user:
            await self._notify_deposit(user.telegram_id, order.amount, tx.balance_after)

        return order

    async def _fulfill_subscription_order(self, order: PaymentOrder) -> bool:
        from src.services import SubscriptionService

        if await self._is_subscription_fulfilled(order):
            return True

        if not order.plan_id:
            logger.error("Subscription payment order %s missing plan_id", order.id)
            return False

        sub_service = SubscriptionService(self.session, self.settings)
        try:
            subscription = await sub_service.extend_subscription(
                order.user_id,
                order.plan_id,
                payment_method=PaymentMethod.YOOKASSA,
                promo_code_id=order.promo_code_id,
                payment_order_id=order.id,
                sync_xray=False,
            )
        except ValueError as exc:
            logger.exception("Failed to fulfill subscription order %s: %s", order.id, exc)
            return False

        user = await self.users.get_by_id(order.user_id)
        if user:
            sub_url = build_subscription_url(
                self.settings.hub_domain, subscription.subscription_token
            )
            plan = await self.plans.get_by_id(order.plan_id)
            await self._notify_purchase(
                telegram_id=user.telegram_id,
                plan_name=plan.name if plan else "Подписка",
                expires_at=format_datetime_ru(subscription.expires_at),
                subscription_url=sub_url,
            )

        return True

    async def check_order(self, order_id: int, user_id: int) -> PaymentOrder | None:
        order = await self.orders.get_by_id(order_id)
        if not order or order.user_id != user_id:
            return None

        if order.status == PaymentStatus.SUCCEEDED:
            if order.purpose == PaymentOrderPurpose.SUBSCRIPTION:
                await self._ensure_subscription_fulfilled(order)
            return order

        return await self.process_payment_success(order.external_id)

    async def _notify_deposit(self, telegram_id: int, amount: Decimal, balance: Decimal) -> None:
        text = (
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"💰 Зачислено: <b>{amount} ₽</b>\n"
            f"💳 Текущий баланс: <b>{balance} ₽</b>"
        )
        await send_telegram_message(self.settings, telegram_id, text)

    async def _notify_purchase(
        self,
        telegram_id: int,
        plan_name: str,
        expires_at: str,
        subscription_url: str,
    ) -> None:
        text = (
            f"✅ <b>Подписка оформлена!</b>\n\n"
            f"💎 Тариф: <b>{plan_name}</b>\n"
            f"📅 Активна до: <b>{expires_at}</b>\n\n"
            f"🔗 Ссылка подписки:\n<code>{subscription_url}</code>"
        )
        await send_telegram_message(self.settings, telegram_id, text)
