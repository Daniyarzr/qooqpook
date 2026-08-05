import hashlib
import logging

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import SubscriptionStatus, SuspensionReason
from src.core.utils import utcnow
from src.models import Subscription, SubscriptionHwid, User
from src.services.notifications import send_telegram_message

logger = logging.getLogger(__name__)

DEVICE_LIMIT_MESSAGE = """
⚠️ <b>Подписка приостановлена</b>

Обнаружено подключение <b>более {max_devices} устройств</b> к вашему аккаунту. По правилам QooQ VPN на одну подписку допускается не более {max_devices} устройств.

<b>Как восстановить доступ:</b>
1️⃣ Откройте бот → 📱 Моя подписка → 📱 Устройства
2️⃣ Удалите лишние устройства
3️⃣ Нажмите «✅ Восстановить подписку»

Если считаете, что это ошибка — напишите в поддержку.
"""


def extract_device_fingerprint(request: Request) -> tuple[str, str | None]:
    user_agent = request.headers.get("user-agent")
    for header in ("x-hwid", "X-HWID", "Hwid", "HTTP-X-HWID"):
        value = request.headers.get(header)
        if value:
            return value.strip()[:128], user_agent

    client_host = request.client.host if request.client else "unknown"
    raw = f"{client_host}:{user_agent or ''}"
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return fingerprint, user_agent


class DeviceLimitService:
    SUSPENSION_REASON = SuspensionReason.DEVICE_LIMIT.value

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    async def count_hwids(self, subscription_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(SubscriptionHwid)
            .where(SubscriptionHwid.subscription_id == subscription_id)
        )
        return result or 0

    async def record_hwid(
        self,
        subscription_id: int,
        hwid: str,
        user_agent: str | None,
    ) -> SubscriptionHwid:
        result = await self.session.execute(
            select(SubscriptionHwid).where(
                SubscriptionHwid.subscription_id == subscription_id,
                SubscriptionHwid.hwid == hwid,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_seen_at = utcnow()
            if user_agent:
                existing.user_agent = user_agent[:512]
            await self.session.flush()
            return existing

        entry = SubscriptionHwid(
            subscription_id=subscription_id,
            hwid=hwid,
            user_agent=user_agent[:512] if user_agent else None,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def check_and_enforce(
        self,
        subscription: Subscription,
        user: User,
        request: Request,
    ) -> bool:
        """Returns True if subscription was suspended."""
        if subscription.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED):
            return subscription.suspension_reason == self.SUSPENSION_REASON

        hwid, user_agent = extract_device_fingerprint(request)
        known = await self.session.execute(
            select(SubscriptionHwid).where(
                SubscriptionHwid.subscription_id == subscription.id,
                SubscriptionHwid.hwid == hwid,
            )
        )
        is_new = known.scalar_one_or_none() is None
        await self.record_hwid(subscription.id, hwid, user_agent)

        if not is_new:
            return False

        count = await self.count_hwids(subscription.id)
        if count <= self.settings.max_devices_per_subscription:
            return False

        return await self.suspend_for_device_limit(subscription, user)

    async def suspend_for_device_limit(self, subscription: Subscription, user: User) -> bool:
        subscription.status = SubscriptionStatus.SUSPENDED
        subscription.suspension_reason = self.SUSPENSION_REASON
        await self.session.flush()

        if subscription.device_limit_notified_at:
            return True

        text = DEVICE_LIMIT_MESSAGE.format(
            max_devices=self.settings.max_devices_per_subscription,
        )
        sent = await send_telegram_message(self.settings, user.telegram_id, text)
        if sent:
            subscription.device_limit_notified_at = utcnow()
            await self.session.flush()

        from src.services import SubscriptionService

        await SubscriptionService(self.session, self.settings).sync_xray_clients()
        logger.info(
            "Subscription %s suspended: device limit exceeded for user %s",
            subscription.id,
            user.id,
        )
        return True

    async def try_reactivate(self, subscription: Subscription) -> bool:
        if subscription.suspension_reason != self.SUSPENSION_REASON:
            return False
        if subscription.status != SubscriptionStatus.SUSPENDED:
            return False

        device_count = len(subscription.devices) if subscription.devices else 0
        if device_count > self.settings.max_devices_per_subscription:
            return False

        await self.clear_hwids(subscription.id)
        subscription.status = (
            SubscriptionStatus.TRIAL if subscription.is_trial else SubscriptionStatus.ACTIVE
        )
        subscription.suspension_reason = None
        subscription.device_limit_notified_at = None
        await self.session.flush()

        from src.services import SubscriptionService

        await SubscriptionService(self.session, self.settings).sync_xray_clients()
        return True

    async def clear_hwids(self, subscription_id: int) -> int:
        result = await self.session.execute(
            select(SubscriptionHwid).where(SubscriptionHwid.subscription_id == subscription_id)
        )
        entries = list(result.scalars().all())
        for entry in entries:
            await self.session.delete(entry)
        await self.session.flush()
        return len(entries)
