import asyncio
import logging
import uuid as uuid_std
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import PaymentMethod, SubscriptionStatus, TransactionType
from src.core.utils import (
    build_subscription_url,
    extend_expiry,
    generate_subscription_token,
    utcnow,
)
from src.models import Subscription, Transaction
from src.repositories import (
    PlanRepository,
    SubscriptionRepository,
    TransactionRepository,
    UserRepository,
)
from src.services.devices import DeviceRepository, DeviceService
from src.services.xray_sync import XrayClient, sync_active_clients

logger = logging.getLogger(__name__)

class SubscriptionService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.plans = PlanRepository(session)
        self.transactions = TransactionRepository(session)

    async def get_user_subscription(self, user_id: int) -> Subscription | None:
        return await self.subscriptions.get_active_by_user(user_id)

    async def activate_trial(self, user_id: int) -> Subscription:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        if user.trial_used:
            raise ValueError("Trial already used")

        now = utcnow()
        subscription = Subscription(
            user_id=user_id,
            status=SubscriptionStatus.TRIAL,
            subscription_token=generate_subscription_token(),
            client_uuid=uuid_std.uuid4(),
            started_at=now,
            expires_at=now + timedelta(days=self.settings.trial_days),
            is_trial=True,
        )
        user.trial_used = True
        await self.subscriptions.create(subscription)
        device_service = DeviceService(self.session, self.settings)
        await device_service.ensure_default_device(subscription)
        await self.sync_xray_clients()
        return subscription

    async def extend_subscription(
        self,
        user_id: int,
        plan_id: int,
        payment_method: PaymentMethod = PaymentMethod.BALANCE,
        promo_code_id: int | None = None,
    ) -> Subscription:
        user = await self.users.get_by_id(user_id)
        plan = await self.plans.get_by_id(plan_id)
        if not user or not plan:
            raise ValueError("User or plan not found")
        if not plan.is_active:
            raise ValueError("Plan is not active")

        from src.services.pricing import PurchasePricingService
        from src.services.promo import PromoCodeService
        from src.services.referral import ReferralService

        pricing = await PurchasePricingService(self.session, self.settings).resolve(
            user_id, plan, promo_code_id
        )
        price = pricing.final_price

        if payment_method == PaymentMethod.BALANCE:
            if user.balance < price:
                raise ValueError("Insufficient balance")
            new_balance = user.balance - price
            await self.users.update_balance(user, new_balance)
            description = f"Оплата подписки: {plan.name}{pricing.description_suffix}"
            await self.transactions.create(
                Transaction(
                    user_id=user.id,
                    type=TransactionType.SUBSCRIPTION_PAYMENT,
                    amount=-price,
                    balance_after=new_balance,
                    description=description,
                    payment_method=payment_method,
                )
            )

        existing = await self.subscriptions.get_active_by_user(user_id)
        now = utcnow()

        referral_service = ReferralService(self.session, self.settings)
        if pricing.referral:
            await referral_service.mark_welcome_used(user, pricing.referral)

        if existing:
            existing.expires_at = extend_expiry(existing.expires_at, plan.days)
            existing.status = SubscriptionStatus.ACTIVE
            existing.is_trial = False
            existing.plan_id = plan.id
            await self.subscriptions.update(existing)
            subscription = existing
        else:
            subscription = Subscription(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                subscription_token=generate_subscription_token(),
                client_uuid=uuid_std.uuid4(),
                started_at=now,
                expires_at=extend_expiry(now, plan.days),
                is_trial=False,
            )
            await self.subscriptions.create(subscription)
            device_service = DeviceService(self.session, self.settings)
            await device_service.ensure_default_device(subscription)

        if pricing.promo:
            await PromoCodeService(self.session).redeem(
                pricing.promo.promo,
                user_id,
                subscription.id,
                pricing.promo,
            )

        await self.sync_xray_clients()
        return subscription

    async def suspend_expired(self) -> int:
        expired = await self.subscriptions.get_expired_active()
        for sub in expired:
            sub.status = SubscriptionStatus.EXPIRED
        await self.session.flush()
        if expired:
            await self.sync_xray_clients()
        return len(expired)

    async def sync_xray_clients(self) -> bool:
        if not self.settings.xray_sync_enabled:
            return False

        active = await self.subscriptions.get_active_with_users()
        device_repo = DeviceRepository(self.session)
        all_devices = await device_repo.get_all_for_active_subscriptions()
        clients = [
            XrayClient(
                user_id=device.subscription.user_id,
                device_id=device.id,
                client_uuid=device.client_uuid,
            )
            for device in all_devices
            if device.subscription
        ]
        return await asyncio.to_thread(sync_active_clients, self.settings, clients)

    def build_hub_data(self, subscription: Subscription | None, bot_username: str) -> dict:
        bot_link = f"https://t.me/{bot_username}"

        if not subscription or subscription.status == SubscriptionStatus.EXPIRED:
            return {
                "active": False,
                "status": SubscriptionStatus.EXPIRED,
                "expires_at": None,
                "expires_at_formatted": None,
                "duration_remaining": None,
                "subscription_url": None,
                "bot_link": bot_link,
                "configs": [],
                "message": "🔒 Подписка не активна. Продлите в боте.",
            }

        if subscription.expires_at <= utcnow():
            return {
                "active": False,
                "status": SubscriptionStatus.EXPIRED,
                "expires_at": subscription.expires_at,
                "expires_at_formatted": subscription.expires_at.strftime("%d.%m.%Y %H:%M"),
                "duration_remaining": "истекла",
                "subscription_url": build_subscription_url(
                    self.settings.hub_domain, subscription.subscription_token
                ),
                "bot_link": bot_link,
                "configs": [],
                "message": "🔒 Подписка истекла. Продлите в боте.",
            }

        from src.core.utils import format_datetime_ru, format_duration_until
        from src.services.vpn_config import build_vless_link, sanitize_remark

        configs = []
        devices = list(subscription.devices) if subscription.devices else []
        user_label = (
            subscription.user.first_name or subscription.user.id
            if subscription.user
            else subscription.user_id
        )
        if devices:
            for device in devices:
                configs.append(
                    build_vless_link(
                        device.client_uuid,
                        sanitize_remark(f"QooQ VPN {user_label} {device.name}"),
                    )
                )
        else:
            configs.append(
                build_vless_link(
                    subscription.client_uuid,
                    sanitize_remark(f"QooQ VPN {user_label}"),
                )
            )

        return {
            "active": True,
            "status": subscription.status,
            "expires_at": subscription.expires_at,
            "expires_at_formatted": format_datetime_ru(subscription.expires_at),
            "duration_remaining": format_duration_until(subscription.expires_at),
            "subscription_url": build_subscription_url(
                self.settings.hub_domain, subscription.subscription_token
            ),
            "bot_link": bot_link,
            "configs": configs,
            "message": "✅ Подписка активна",
        }


class BalanceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.transactions = TransactionRepository(session)

    async def add_balance(
        self,
        user_id: int,
        amount: Decimal,
        description: str,
        tx_type: TransactionType = TransactionType.DEPOSIT,
        payment_method: PaymentMethod | None = None,
    ) -> Transaction:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        new_balance = user.balance + amount
        await self.users.update_balance(user, new_balance)
        return await self.transactions.create(
            Transaction(
                user_id=user_id,
                type=tx_type,
                amount=amount,
                balance_after=new_balance,
                description=description,
                payment_method=payment_method,
            )
        )

    async def get_history(self, user_id: int, limit: int = 20) -> list[Transaction]:
        return await self.transactions.get_by_user(user_id, limit)
