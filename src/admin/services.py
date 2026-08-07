from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import Settings
from src.core.enums import PaymentStatus, ServerStatus, SubscriptionStatus, TransactionType, VpnConfigType
from src.core.utils import build_subscription_url, bytes_to_gb, format_bytes, utcnow
from src.models import (
    AdminUser,
    PaymentOrder,
    PromoCode,
    PromoCodeRedemption,
    ReferralReward,
    Subscription,
    SubscriptionDevice,
    SubscriptionPlan,
    SystemSetting,
    Transaction,
    User,
    VpnConfig,
    VpnServer,
)
from src.services.traffic_sync import (
    TrafficSyncService,
    get_traffic_limit_gb,
    get_traffic_total_bytes,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _money(value) -> Decimal:
    return abs(Decimal(value or 0)).quantize(Decimal("0.01"))


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
        now = utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        async def count_users(since=None, banned: bool | None = None) -> int:
            q = select(func.count()).select_from(User)
            if since:
                q = q.where(User.created_at >= since)
            if banned is not None:
                q = q.where(User.is_banned.is_(banned))
            return (await self.session.scalar(q)) or 0

        async def count_subs(statuses, since=None, not_expired: bool = False) -> int:
            q = select(func.count()).select_from(Subscription).where(Subscription.status.in_(statuses))
            if not_expired:
                q = q.where(Subscription.expires_at > now)
            if since:
                q = q.where(Subscription.created_at >= since)
            return (await self.session.scalar(q)) or 0

        async def sum_tx(types, since=None, absolute: bool = False) -> Decimal:
            q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type.in_(types if isinstance(types, list) else [types])
            )
            if since:
                q = q.where(Transaction.created_at >= since)
            value = await self.session.scalar(q)
            amount = Decimal(value or 0)
            return _money(amount) if absolute else amount

        async def sum_payment_orders(since=None) -> Decimal:
            q = (
                select(func.coalesce(func.sum(PaymentOrder.amount), 0))
                .where(PaymentOrder.status == PaymentStatus.SUCCEEDED)
            )
            if since:
                q = q.where(PaymentOrder.paid_at >= since)
            return _money(await self.session.scalar(q))

        async def count_payment_orders(status=None, since=None) -> int:
            q = select(func.count()).select_from(PaymentOrder)
            if status:
                q = q.where(PaymentOrder.status == status)
            if since:
                q = q.where(PaymentOrder.created_at >= since)
            return (await self.session.scalar(q)) or 0

        async def sum_promo_discounts(since=None) -> Decimal:
            q = select(func.coalesce(func.sum(PromoCodeRedemption.discount_amount), 0))
            if since:
                q = q.where(PromoCodeRedemption.created_at >= since)
            return _money(await self.session.scalar(q))

        async def count_promo_redemptions(since=None) -> int:
            q = select(func.count()).select_from(PromoCodeRedemption)
            if since:
                q = q.where(PromoCodeRedemption.created_at >= since)
            return (await self.session.scalar(q)) or 0

        total_users = await count_users()
        banned_users = await count_users(banned=True)
        paying_users = await self.session.scalar(
            select(func.count(func.distinct(Transaction.user_id))).where(
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT
            )
        )

        active_subs = await count_subs(
            [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL], not_expired=True
        )
        trial_subs = await count_subs([SubscriptionStatus.TRIAL], not_expired=True)
        paid_active_subs = await count_subs([SubscriptionStatus.ACTIVE], not_expired=True)
        suspended_subs = await count_subs([SubscriptionStatus.SUSPENDED])
        expired_subs = await count_subs([SubscriptionStatus.EXPIRED])

        total_revenue = await sum_tx(TransactionType.SUBSCRIPTION_PAYMENT, absolute=True)
        revenue_today = await sum_tx(TransactionType.SUBSCRIPTION_PAYMENT, day_ago, absolute=True)
        revenue_7d = await sum_tx(TransactionType.SUBSCRIPTION_PAYMENT, week_ago, absolute=True)
        revenue_30d = await sum_tx(TransactionType.SUBSCRIPTION_PAYMENT, month_ago, absolute=True)

        total_deposits = await sum_tx([TransactionType.DEPOSIT], absolute=True)
        deposits_today = await sum_tx([TransactionType.DEPOSIT], day_ago, absolute=True)
        deposits_7d = await sum_tx([TransactionType.DEPOSIT], week_ago, absolute=True)
        deposits_30d = await sum_tx([TransactionType.DEPOSIT], month_ago, absolute=True)

        yookassa_total = await sum_payment_orders()
        yookassa_30d = await sum_payment_orders(month_ago)

        referral_paid = await sum_tx(TransactionType.REFERRAL_BONUS, absolute=True)
        referral_paid_30d = await sum_tx(TransactionType.REFERRAL_BONUS, month_ago, absolute=True)

        promo_discount_total = await sum_promo_discounts()
        promo_discount_30d = await sum_promo_discounts(month_ago)
        promo_redemptions = await count_promo_redemptions()
        active_promos = await self.session.scalar(
            select(func.count()).select_from(PromoCode).where(PromoCode.is_active.is_(True))
        )

        total_balance = await self.session.scalar(select(func.coalesce(func.sum(User.balance), 0)))
        admin_adjustments = await sum_tx(TransactionType.ADMIN_ADJUSTMENT)
        admin_adjustments_abs = _money(admin_adjustments)

        pending_orders = await count_payment_orders(PaymentStatus.PENDING)
        pending_orders_sum = _money(
            await self.session.scalar(
                select(func.coalesce(func.sum(PaymentOrder.amount), 0)).where(
                    PaymentOrder.status == PaymentStatus.PENDING
                )
            )
        )
        succeeded_orders = await count_payment_orders(PaymentStatus.SUCCEEDED)

        traffic_bytes = await self.session.scalar(
            select(
                func.coalesce(func.sum(Subscription.bytes_upload + Subscription.bytes_download), 0)
            )
        )
        referrals_count = await self.session.scalar(select(func.count()).select_from(ReferralReward))
        trial_used_count = await self.session.scalar(
            select(func.count()).select_from(User).where(User.trial_used.is_(True))
        )

        conversion = round(paying_users / total_users * 100, 1) if total_users else 0
        arpu = _money(total_revenue / paying_users) if paying_users else Decimal("0.00")

        # Daily charts — last 14 days
        chart_start = now - timedelta(days=13)
        chart_start = chart_start.replace(hour=0, minute=0, second=0, microsecond=0)

        revenue_rows = await self.session.execute(
            select(
                func.date(Transaction.created_at).label("day"),
                func.coalesce(func.sum(Transaction.amount), 0).label("amount"),
            )
            .where(
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT,
                Transaction.created_at >= chart_start,
            )
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
        )
        revenue_by_day = {str(row.day): _money(row.amount) for row in revenue_rows}

        users_rows = await self.session.execute(
            select(
                func.date(User.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(User.created_at >= chart_start)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        users_by_day = {str(row.day): row.cnt for row in users_rows}

        revenue_chart = []
        users_chart = []
        max_revenue = Decimal("1")
        max_users = 1
        for i in range(14):
            day = (chart_start + timedelta(days=i)).date()
            day_str = str(day)
            rev = revenue_by_day.get(day_str, Decimal("0"))
            usr = users_by_day.get(day_str, 0)
            max_revenue = max(max_revenue, rev)
            max_users = max(max_users, usr)
            revenue_chart.append({"date": day.strftime("%d.%m"), "amount": rev, "label": day_str})
            users_chart.append({"date": day.strftime("%d.%m"), "count": usr, "label": day_str})

        for item in revenue_chart:
            item["pct"] = float(item["amount"] / max_revenue * 100) if max_revenue else 0
        for item in users_chart:
            item["pct"] = item["count"] / max_users * 100 if max_users else 0

        # Subscriptions by plan
        plan_rows = await self.session.execute(
            select(
                SubscriptionPlan.name,
                SubscriptionPlan.price,
                func.count(Subscription.id).label("cnt"),
            )
            .select_from(Subscription)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                Subscription.expires_at > now,
            )
            .group_by(SubscriptionPlan.id, SubscriptionPlan.name, SubscriptionPlan.price)
            .order_by(func.count(Subscription.id).desc())
        )
        subs_by_plan = [
            {"name": row.name, "price": row.price, "count": row.cnt or 0}
            for row in plan_rows
            if row.cnt
        ]

        # Recent transactions
        recent_result = await self.session.execute(
            select(Transaction, User)
            .join(User, User.id == Transaction.user_id)
            .order_by(Transaction.created_at.desc())
            .limit(15)
        )
        recent_transactions = [
            {
                "id": tx.id,
                "user_id": user.id,
                "user_name": user.first_name or user.username or f"#{user.id}",
                "type": tx.type.value,
                "amount": tx.amount,
                "balance_after": tx.balance_after,
                "description": tx.description,
                "created_at": tx.created_at,
            }
            for tx, user in recent_result.all()
        ]

        return {
            "generated_at": now,
            "users": {
                "total": total_users,
                "banned": banned_users,
                "active": total_users - banned_users,
                "new_today": await count_users(day_ago),
                "new_7d": await count_users(week_ago),
                "new_30d": await count_users(month_ago),
                "paying": paying_users or 0,
                "trial_used": trial_used_count or 0,
                "conversion_pct": conversion,
            },
            "subscriptions": {
                "active": active_subs,
                "paid_active": paid_active_subs,
                "trial": trial_subs,
                "suspended": suspended_subs,
                "expired": expired_subs,
                "new_7d": await count_subs(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL], week_ago
                ),
                "new_30d": await count_subs(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL], month_ago
                ),
                "by_plan": subs_by_plan,
            },
            "finance": {
                "revenue_total": total_revenue,
                "revenue_today": revenue_today,
                "revenue_7d": revenue_7d,
                "revenue_30d": revenue_30d,
                "deposits_total": total_deposits,
                "deposits_today": deposits_today,
                "deposits_7d": deposits_7d,
                "deposits_30d": deposits_30d,
                "yookassa_total": yookassa_total,
                "yookassa_30d": yookassa_30d,
                "referral_paid": referral_paid,
                "referral_paid_30d": referral_paid_30d,
                "promo_discounts": promo_discount_total,
                "promo_discounts_30d": promo_discount_30d,
                "user_balances": _money(total_balance),
                "admin_adjustments": admin_adjustments,
                "admin_adjustments_abs": admin_adjustments_abs,
                "pending_orders": pending_orders,
                "pending_orders_sum": pending_orders_sum,
                "succeeded_orders": succeeded_orders,
                "arpu": arpu,
                "net_after_referrals": _money(total_revenue - referral_paid),
            },
            "promo": {
                "active_codes": active_promos or 0,
                "redemptions": promo_redemptions,
            },
            "infrastructure": {
                "active_servers": (
                    await self.session.scalar(
                        select(func.count()).select_from(VpnServer).where(VpnServer.is_active.is_(True))
                    )
                )
                or 0,
                "traffic_gb": bytes_to_gb(traffic_bytes or 0),
                "referrals": referrals_count or 0,
            },
            "charts": {
                "revenue": revenue_chart,
                "users": users_chart,
            },
            "recent_transactions": recent_transactions,
        }

    async def list_users(self, offset: int = 0, limit: int = 50) -> list[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.subscriptions))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    @staticmethod
    def get_manageable_subscription(user: User) -> Subscription | None:
        for sub in sorted(user.subscriptions, key=lambda item: item.created_at, reverse=True):
            if sub.status in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.SUSPENDED,
            ):
                return sub
        return None

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(
                selectinload(User.subscriptions).selectinload(Subscription.plan),
                selectinload(User.subscriptions).selectinload(Subscription.devices),
                selectinload(User.subscriptions).selectinload(Subscription.hwids),
                selectinload(User.transactions),
                selectinload(User.payment_orders),
                selectinload(User.referred_by),
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def build_traffic_info(subscription: Subscription | None) -> dict:
        if not subscription:
            return {
                "upload_gb": 0,
                "download_gb": 0,
                "total_gb": 0,
                "limit_gb": None,
                "used_percent": None,
                "upload_human": "0 B",
                "download_human": "0 B",
                "total_human": "0 B",
                "last_sync": None,
            }

        limit_gb = get_traffic_limit_gb(subscription)
        total_bytes = get_traffic_total_bytes(subscription)
        total_gb = bytes_to_gb(total_bytes)
        used_percent = None
        if limit_gb:
            used_percent = min(100, round(total_gb / limit_gb * 100, 1))

        return {
            "upload_gb": bytes_to_gb(subscription.bytes_upload),
            "download_gb": bytes_to_gb(subscription.bytes_download),
            "total_gb": total_gb,
            "limit_gb": limit_gb,
            "used_percent": used_percent,
            "upload_human": format_bytes(subscription.bytes_upload),
            "download_human": format_bytes(subscription.bytes_download),
            "total_human": format_bytes(total_bytes),
            "last_sync": subscription.last_traffic_sync_at,
        }

    async def sync_user_traffic(self, user_id: int, settings: Settings) -> bool:
        from src.services.config_credentials import ConfigCredentialService
        from src.services.devices import DeviceRepository

        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        subscription = self.get_manageable_subscription(user)
        if not subscription:
            return False

        devices = await DeviceRepository(self.session).get_by_subscription(subscription.id)
        sync = TrafficSyncService(settings)
        traffic_list = sync.fetch_all_traffic()
        cred_map = await ConfigCredentialService(self.session).credential_device_map(
            [subscription.id]
        )
        updated = sync.apply_traffic_to_subscription(
            subscription, traffic_list, devices, cred_map
        )
        if updated:
            await self.session.flush()
        return updated

    async def sync_all_traffic(self, settings: Settings) -> int:
        from src.repositories import SubscriptionRepository
        from src.services.config_credentials import ConfigCredentialService
        from src.services.devices import DeviceRepository

        if not settings.xray_stats_enabled:
            return 0

        sync = TrafficSyncService(settings)
        traffic_list = sync.fetch_all_traffic()
        if not traffic_list:
            return 0

        subs_repo = SubscriptionRepository(self.session)
        device_repo = DeviceRepository(self.session)
        active = await subs_repo.get_active_with_users()
        cred_map = await ConfigCredentialService(self.session).credential_device_map(
            [item.id for item in active]
        )
        updated = 0
        for subscription in active:
            devices = await device_repo.get_by_subscription(subscription.id)
            if sync.apply_traffic_to_subscription(
                subscription, traffic_list, devices, cred_map
            ):
                updated += 1

        if updated:
            await self.session.flush()
        return updated

    async def reset_user_traffic(self, user_id: int) -> bool:
        from src.services.devices import DeviceRepository

        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        subscription = self.get_manageable_subscription(user)
        if not subscription:
            return False

        devices = await DeviceRepository(self.session).get_by_subscription(subscription.id)
        for device in devices:
            device.bytes_upload = 0
            device.bytes_download = 0
            device.traffic_baseline_upload = 0
            device.traffic_baseline_download = 0

        subscription.bytes_upload = 0
        subscription.bytes_download = 0
        subscription.traffic_baseline_upload = 0
        subscription.traffic_baseline_download = 0
        subscription.last_traffic_sync_at = utcnow()
        await self.session.flush()
        return True

    async def add_user_device(self, user_id: int, settings: Settings):
        from src.services import SubscriptionService
        from src.services.devices import DeviceService

        user = await self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        subscription = self.get_manageable_subscription(user)
        if not subscription:
            raise ValueError("Active subscription not found")

        device_service = DeviceService(self.session, settings)
        device = await device_service.add_device(subscription)
        sub_service = SubscriptionService(self.session, settings)
        await sub_service.sync_xray_clients()
        return device

    async def delete_user_device(self, user_id: int, device_id: int, settings: Settings) -> bool:
        from src.services import SubscriptionService
        from src.services.devices import DeviceService

        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        subscription = self.get_manageable_subscription(user)
        if not subscription:
            return False

        device_service = DeviceService(self.session, settings)
        deleted = await device_service.delete_device(device_id, subscription.id)
        if not deleted:
            return False

        sub_service = SubscriptionService(self.session, settings)
        await sub_service.sync_xray_clients()

        from src.services.device_limit import DeviceLimitService

        limit_service = DeviceLimitService(self.session, settings)
        await limit_service.try_reactivate(subscription)
        return True

    async def clear_user_hwids(self, user_id: int, settings: Settings) -> int:
        from src.services.device_limit import DeviceLimitService

        user = await self.get_user_by_id(user_id)
        if not user:
            return 0
        subscription = self.get_manageable_subscription(user)
        if not subscription:
            return 0

        limit_service = DeviceLimitService(self.session, settings)
        return await limit_service.clear_hwids(subscription.id)

    async def reactivate_user_subscription(self, user_id: int, settings: Settings) -> bool:
        from src.services.device_limit import DeviceLimitService

        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        subscription = self.get_manageable_subscription(user)
        if not subscription:
            return False

        limit_service = DeviceLimitService(self.session, settings)
        return await limit_service.try_reactivate(subscription)

    async def extend_user_subscription(self, user_id: int, days: int, settings: Settings) -> bool:
        from src.core.utils import extend_expiry
        from src.repositories import SubscriptionRepository
        from src.services import SubscriptionService

        if days <= 0:
            return False

        subs = SubscriptionRepository(self.session)
        subscription = await subs.get_manageable_by_user(user_id)
        if not subscription:
            return False

        subscription.expires_at = extend_expiry(subscription.expires_at, days)
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.is_trial = False
        await self.session.flush()

        service = SubscriptionService(self.session, settings)
        await service.sync_xray_clients()
        return True

    async def ban_user(self, user_id: int, banned: bool = True) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = banned
            await self.session.flush()
        return user

    async def deactivate_user_subscription(self, user_id: int, settings: Settings) -> bool:
        from src.repositories import SubscriptionRepository
        from src.services import SubscriptionService

        subs = SubscriptionRepository(self.session)
        subscription = await subs.get_manageable_by_user(user_id)
        if not subscription:
            return False

        subscription.status = SubscriptionStatus.SUSPENDED
        await self.session.flush()

        from src.services.config_credentials import ConfigCredentialService

        await ConfigCredentialService(self.session, settings).revoke_subscription(subscription.id)
        await self.session.flush()

        service = SubscriptionService(self.session, settings)
        await service.sync_xray_clients()
        return True

    async def delete_user_subscription(self, user_id: int, settings: Settings) -> bool:
        from src.repositories import SubscriptionRepository
        from src.services import SubscriptionService

        subs = SubscriptionRepository(self.session)
        subscription = await subs.get_manageable_by_user(user_id)
        if not subscription:
            return False

        await subs.delete(subscription)

        service = SubscriptionService(self.session, settings)
        await service.sync_xray_clients()
        return True

    async def adjust_balance(self, user_id: int, amount: Decimal, description: str) -> None:
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
            select(VpnServer)
            .options(selectinload(VpnServer.configs))
            .order_by(VpnServer.sort_order, VpnServer.id)
        )
        return list(result.scalars().unique().all())

    async def get_server_by_id(self, server_id: int) -> VpnServer | None:
        result = await self.session.execute(
            select(VpnServer)
            .options(selectinload(VpnServer.configs))
            .where(VpnServer.id == server_id)
        )
        return result.scalar_one_or_none()

    async def _get_primary_server_id(self) -> int | None:
        result = await self.session.execute(
            select(VpnServer.id)
            .where(VpnServer.is_active.is_(True))
            .order_by(VpnServer.sort_order, VpnServer.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_server_stats(self, server: VpnServer) -> dict:
        now = utcnow()
        config_ids = [config.id for config in server.configs]
        primary_id = await self._get_primary_server_id()
        include_unassigned = primary_id == server.id

        base_filter = [
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            Subscription.expires_at > now,
        ]
        if config_ids and include_unassigned:
            assignment = (
                (Subscription.config_id.in_(config_ids))
                | (Subscription.config_id.is_(None))
            )
        elif config_ids:
            assignment = Subscription.config_id.in_(config_ids)
        elif include_unassigned:
            assignment = Subscription.config_id.is_(None)
        else:
            assignment = Subscription.config_id.in_([-1])

        users_count = await self.session.scalar(
            select(func.count(func.distinct(Subscription.user_id)))
            .where(assignment, *base_filter)
        )

        subs_count = await self.session.scalar(
            select(func.count()).select_from(Subscription).where(assignment, *base_filter)
        )

        devices_count = await self.session.scalar(
            select(func.count())
            .select_from(SubscriptionDevice)
            .join(Subscription, Subscription.id == SubscriptionDevice.subscription_id)
            .where(assignment, *base_filter)
        )

        traffic_row = await self.session.execute(
            select(
                func.coalesce(func.sum(Subscription.bytes_upload), 0),
                func.coalesce(func.sum(Subscription.bytes_download), 0),
            )
            .where(assignment, *base_filter)
        )
        upload_bytes, download_bytes = traffic_row.one()

        connected = users_count or 0
        max_users = server.max_users or 1
        load_percent = min(100, round(connected / max_users * 100, 1))
        total_bytes = (upload_bytes or 0) + (download_bytes or 0)

        if server.current_users != connected:
            server.current_users = connected
            await self.session.flush()

        return {
            "connected_users": connected,
            "subscriptions_count": subs_count or 0,
            "devices_count": devices_count or 0,
            "upload_gb": bytes_to_gb(upload_bytes or 0),
            "download_gb": bytes_to_gb(download_bytes or 0),
            "total_traffic_gb": bytes_to_gb(total_bytes),
            "upload_human": format_bytes(upload_bytes or 0),
            "download_human": format_bytes(download_bytes or 0),
            "total_traffic_human": format_bytes(total_bytes),
            "load_percent": load_percent,
            "slots_free": max(0, max_users - connected),
            "includes_unassigned": include_unassigned,
        }

    async def list_servers_with_stats(self) -> list[dict]:
        servers = await self.list_servers()
        rows = []
        for server in servers:
            stats = await self.get_server_stats(server)
            rows.append({"server": server, "stats": stats})
        return rows

    async def create_server(
        self,
        name: str,
        country: str,
        host: str,
        country_flag: str = "🌍",
        port: int = 443,
        protocol: str = "vless",
        max_users: int = 1000,
        status: str = "online",
        sort_order: int = 0,
    ) -> VpnServer:
        if not name.strip() or not host.strip():
            raise ValueError("Название и хост обязательны")
        if max_users <= 0:
            raise ValueError("Лимит пользователей должен быть больше 0")

        server = VpnServer(
            name=name.strip(),
            country=country.strip() or "Unknown",
            country_flag=country_flag.strip() or "🌍",
            host=host.strip(),
            port=port,
            protocol=protocol.strip() or "vless",
            max_users=max_users,
            status=ServerStatus(status),
            sort_order=sort_order,
            is_active=True,
        )
        self.session.add(server)
        await self.session.flush()

        config = VpnConfig(
            server_id=server.id,
            name=f"{server.name} VLESS",
            config_type=VpnConfigType.VLESS_LINK,
            config_template="vless://{uuid}@{host}:{port}?type=tcp&security=reality#{name}",
        )
        self.session.add(config)
        await self.session.flush()

        from src.services.vpn_config_store import VpnConfigStore, export_default_json_template

        await VpnConfigStore(self.session).create_config(
            server_id=server.id,
            name=f"{server.name} Xray JSON",
            config_type=VpnConfigType.XRAY_JSON,
            config_template=export_default_json_template(),
            is_default=True,
        )
        return server

    async def list_configs_with_stats(self) -> list[dict]:
        from src.services.vpn_config_store import VpnConfigStore

        store = VpnConfigStore(self.session)
        configs = await store.list_configs()
        rows = []
        for config in configs:
            subs_count = await self.session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.config_id == config.id)
            )
            rows.append({"config": config, "subscriptions_count": subs_count or 0})
        return rows

    async def get_config_by_id(self, config_id: int) -> VpnConfig | None:
        from src.services.vpn_config_store import VpnConfigStore

        return await VpnConfigStore(self.session).get_by_id(config_id)

    async def create_vpn_config(
        self,
        server_id: int,
        name: str,
        config_type: str,
        config_template: str,
        is_default: bool = False,
    ) -> VpnConfig:
        from src.services.vpn_config_store import VpnConfigStore

        server = await self.get_server_by_id(server_id)
        if not server:
            raise ValueError("Сервер не найден")
        return await VpnConfigStore(self.session).create_config(
            server_id=server_id,
            name=name,
            config_type=VpnConfigType(config_type),
            config_template=config_template,
            is_default=is_default,
        )

    async def update_vpn_config(
        self,
        config_id: int,
        *,
        name: str | None = None,
        config_template: str | None = None,
        is_default: bool | None = None,
        is_active: bool | None = None,
    ) -> VpnConfig | None:
        from src.services.vpn_config_store import VpnConfigStore

        return await VpnConfigStore(self.session).update_config(
            config_id,
            name=name,
            config_template=config_template,
            is_default=is_default,
            is_active=is_active,
        )

    async def delete_vpn_config(self, config_id: int) -> bool:
        from src.services.vpn_config_store import VpnConfigStore

        return await VpnConfigStore(self.session).delete_config(config_id)

    async def delete_server(self, server_id: int) -> bool:
        server = await self.get_server_by_id(server_id)
        if not server:
            return False

        config_ids = [config.id for config in server.configs]
        if config_ids:
            linked = await self.session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.config_id.in_(config_ids))
            )
            if linked:
                raise ValueError(
                    f"Нельзя удалить: {linked} подписок привязаны к серверу"
                )

        await self.session.delete(server)
        await self.session.flush()
        return True

    async def update_server(
        self,
        server_id: int,
        *,
        name: str | None = None,
        country: str | None = None,
        country_flag: str | None = None,
        host: str | None = None,
        port: int | None = None,
        protocol: str | None = None,
        max_users: int | None = None,
        status: str | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> VpnServer | None:
        server = await self.get_server_by_id(server_id)
        if not server:
            return None
        if name is not None:
            server.name = name.strip()
        if country is not None:
            server.country = country.strip()
        if country_flag is not None:
            server.country_flag = country_flag.strip() or "🌍"
        if host is not None:
            server.host = host.strip()
        if port is not None:
            server.port = port
        if protocol is not None:
            server.protocol = protocol.strip()
        if max_users is not None:
            if max_users <= 0:
                raise ValueError("Лимит пользователей должен быть больше 0")
            server.max_users = max_users
        if status is not None:
            server.status = ServerStatus(status)
        if sort_order is not None:
            server.sort_order = sort_order
        if is_active is not None:
            server.is_active = is_active
        await self.session.flush()
        return server

    async def list_promo_codes(self):
        from src.services.promo import PromoCodeRepository

        return await PromoCodeRepository(self.session).list_all()

    async def create_promo_code(
        self,
        code: str,
        discount_type: str,
        discount_value: Decimal,
        description: str | None = None,
        plan_id: int | None = None,
        max_uses: int | None = None,
        max_uses_per_user: int = 1,
        valid_until=None,
    ):
        from src.core.enums import PromoDiscountType
        from src.services.promo import PromoCodeService

        dtype = PromoDiscountType(discount_type)
        return await PromoCodeService(self.session).create_promo(
            code=code,
            discount_type=dtype,
            discount_value=discount_value,
            description=description or None,
            plan_id=plan_id,
            max_uses=max_uses,
            max_uses_per_user=max_uses_per_user,
            valid_until=valid_until,
        )

    async def toggle_promo_code(self, promo_id: int):
        from src.services.promo import PromoCodeService

        return await PromoCodeService(self.session).toggle_active(promo_id)

    async def delete_promo_code(self, promo_id: int) -> bool:
        from src.services.promo import PromoCodeService

        return await PromoCodeService(self.session).delete_promo(promo_id)

    async def get_referral_bonus_percent(self, settings: Settings) -> int:
        from src.services.system_settings import SystemSettingsService

        return await SystemSettingsService(self.session, settings).get_referral_bonus_percent()

    async def set_referral_bonus_percent(self, settings: Settings, percent: int) -> int:
        from src.services.system_settings import SystemSettingsService

        return await SystemSettingsService(self.session, settings).set_referral_bonus_percent(
            percent
        )

    async def get_referral_discount_percent(self, settings: Settings) -> int:
        return await self.get_referral_bonus_percent(settings)

    async def set_referral_discount_percent(self, settings: Settings, percent: int) -> int:
        return await self.set_referral_bonus_percent(settings, percent)
