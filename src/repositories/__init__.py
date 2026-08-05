from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.enums import SubscriptionStatus
from src.core.utils import generate_referral_code, utcnow
from src.models import PaymentOrder, Subscription, SubscriptionPlan, Transaction, User, VpnServer


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.referral_code == code.upper())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referred_by_id: int | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            referral_code=generate_referral_code(),
            referred_by_id=referred_by_id,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_balance(self, user: User, new_balance) -> User:
        user.balance = new_balance
        await self.session.flush()
        return user


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_by_user(self, user_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if sub and sub.expires_at <= utcnow():
            sub.status = SubscriptionStatus.EXPIRED
            await self.session.flush()
            return None
        return sub

    async def get_by_token(self, token: str) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.user),
                selectinload(Subscription.config),
                selectinload(Subscription.plan),
                selectinload(Subscription.devices),
            )
            .where(Subscription.subscription_token == token)
        )
        return result.scalar_one_or_none()

    async def create(self, subscription: Subscription) -> Subscription:
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def update(self, subscription: Subscription) -> Subscription:
        await self.session.flush()
        return subscription

    async def get_expired_active(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .where(Subscription.expires_at <= utcnow())
        )
        return list(result.scalars().all())

    async def get_active_with_users(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .where(Subscription.expires_at > utcnow())
        )
        return list(result.scalars().all())

    async def get_manageable_by_user(self, user_id: int) -> Subscription | None:
        """Active, trial, or device-limit suspended subscription."""
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(
                Subscription.status.in_(
                    [
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIAL,
                        SubscriptionStatus.SUSPENDED,
                    ]
                )
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_current_by_user(self, user_id: int) -> Subscription | None:
        """Latest subscription including suspended (for bot UI)."""
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.devices))
            .where(Subscription.user_id == user_id)
            .where(
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL, SubscriptionStatus.SUSPENDED]
                )
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if sub and sub.expires_at <= utcnow() and sub.status != SubscriptionStatus.SUSPENDED:
            sub.status = SubscriptionStatus.EXPIRED
            await self.session.flush()
            return None
        return sub

    async def delete(self, subscription: Subscription) -> None:
        await self.session.delete(subscription)
        await self.session.flush()


class PlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_plans(self) -> list[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price)
        )
        return list(result.scalars().all())

    async def get_by_id(self, plan_id: int) -> SubscriptionPlan | None:
        result = await self.session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        return result.scalar_one_or_none()


class TransactionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def get_by_user(self, user_id: int, limit: int = 20) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class ServerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_servers(self) -> list[VpnServer]:
        result = await self.session.execute(
            select(VpnServer)
            .where(VpnServer.is_active.is_(True))
            .order_by(VpnServer.sort_order, VpnServer.name)
        )
        return list(result.scalars().all())


class PaymentOrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, order: PaymentOrder) -> PaymentOrder:
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: int) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.external_id == external_id)
        )
        return result.scalar_one_or_none()
