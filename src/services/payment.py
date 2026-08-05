import logging
import uuid
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import PaymentMethod, PaymentStatus, TransactionType
from src.core.utils import utcnow
from src.models import PaymentOrder
from src.repositories import PaymentOrderRepository, UserRepository
from src.services import BalanceService
from src.services.yookassa import YooKassaClient, YooKassaError

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.orders = PaymentOrderRepository(session)
        self.users = UserRepository(session)
        self.balance = BalanceService(session)
        self.yookassa = YooKassaClient(settings)

    async def create_deposit(self, user_id: int, amount: Decimal) -> PaymentOrder:
        if not self.yookassa.enabled:
            raise ValueError("YooKassa is not configured")

        if amount < Decimal(self.settings.deposit_min_amount):
            raise ValueError(f"Minimum deposit is {self.settings.deposit_min_amount} ₽")
        if amount > Decimal(self.settings.deposit_max_amount):
            raise ValueError(f"Maximum deposit is {self.settings.deposit_max_amount} ₽")

        user = await self.users.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        order = await self.orders.create(
            PaymentOrder(
                user_id=user_id,
                amount=amount,
                external_id=str(uuid.uuid4()),
                status=PaymentStatus.PENDING,
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

    async def process_payment_success(self, external_id: str) -> PaymentOrder | None:
        order = await self.orders.get_by_external_id(external_id)
        if not order:
            logger.warning("Payment order not found for external_id=%s", external_id)
            return None

        if order.status == PaymentStatus.SUCCEEDED:
            return order

        try:
            payment = await self.yookassa.get_payment(external_id)
        except YooKassaError:
            return None

        if payment.get("status") != "succeeded":
            return None

        paid_amount = Decimal(payment["amount"]["value"])
        if paid_amount != order.amount:
            logger.error(
                "Payment amount mismatch: order=%s paid=%s external_id=%s",
                order.amount,
                paid_amount,
                external_id,
            )
            return None

        order.status = PaymentStatus.SUCCEEDED
        order.paid_at = utcnow()
        await self.session.flush()

        tx = await self.balance.add_balance(
            user_id=order.user_id,
            amount=order.amount,
            description=f"Пополнение через ЮKassa (#{order.id})",
            payment_method=PaymentMethod.YOOKASSA,
        )

        user = await self.users.get_by_id(order.user_id)
        if user and self.settings.bot_token:
            await self._notify_user(
                telegram_id=user.telegram_id,
                amount=order.amount,
                balance=tx.balance_after,
            )

        return order

    async def check_order(self, order_id: int, user_id: int) -> PaymentOrder | None:
        order = await self.orders.get_by_id(order_id)
        if not order or order.user_id != user_id:
            return None

        if order.status == PaymentStatus.SUCCEEDED:
            return order

        return await self.process_payment_success(order.external_id)

    async def _notify_user(self, telegram_id: int, amount: Decimal, balance: Decimal) -> None:
        text = (
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"💰 Зачислено: <b>{amount} ₽</b>\n"
            f"💳 Текущий баланс: <b>{balance} ₽</b>"
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
            logger.exception("Failed to notify user %s about deposit", telegram_id)
