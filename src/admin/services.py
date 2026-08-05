from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import SubscriptionStatus, TransactionType
from src.models import (
    AdminUser,
    Subscription,
    SubscriptionPlan,
    Transaction,
    User,
    VpnServer,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


class AdminService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, username: str, password: str) -> AdminUser | None:
        result = await self.session.execute(
            select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True))
        )
        admin = result.scalar_one_or_none()
        if admin and verify_password(password, admin.password_hash):
            admin.last_login_at = datetime.now(timezone.utc)
            await self.session.flush()
            return admin
        return None

    async def get_dashboard_stats(self) -> dict:
        now = datetime.now(timezone.utc)

        total_users = await self.session.scalar(select(func.count()).select_from(User))
        active_subs = await self.session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .where(Subscription.expires_at > now)
        )
        expired_subs = await self.session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SubscriptionStatus.EXPIRED)
        )
        total_revenue = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT
            )
        )
        total_balance = await self.session.scalar(
            select(func.coalesce(func.sum(User.balance), 0))
        )
        total_servers = await self.session.scalar(
            select(func.count()).select_from(VpnServer).where(VpnServer.is_active.is_(True))
        )
        new_users_7d = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.created_at >= now - timedelta(days=7))
        )

        return {
            "total_users": total_users or 0,
            "active_subscriptions": active_subs or 0,
            "expired_subscriptions": expired_subs or 0,
            "total_revenue": abs(total_revenue or 0),
            "total_balance": total_balance or 0,
            "active_servers": total_servers or 0,
            "new_users_7d": new_users_7d or 0,
        }

    async def list_users(self, offset: int = 0, limit: int = 50) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def ban_user(self, user_id: int, banned: bool = True) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = banned
            await self.session.flush()
        return user

    async def adjust_balance(self, user_id: int, amount: Decimal, description: str) -> None:
        from src.core.enums import SubscriptionStatus, TransactionType
        from src.services import BalanceService

        service = BalanceService(self.session)
        await service.add_balance(
            user_id,
            amount,
            description,
            tx_type=TransactionType.ADMIN_ADJUSTMENT,
        )

    async def list_plans(self) -> list[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order)
        )
        return list(result.scalars().all())

    async def list_servers(self) -> list[VpnServer]:
        result = await self.session.execute(
            select(VpnServer).order_by(VpnServer.sort_order)
        )
        return list(result.scalars().all())
