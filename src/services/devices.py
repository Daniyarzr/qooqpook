import uuid as uuid_std
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import Settings
from src.core.enums import SubscriptionStatus
from src.core.utils import utcnow
from src.models import Subscription, SubscriptionDevice

logger = logging.getLogger(__name__)


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, device_id: int) -> SubscriptionDevice | None:
        result = await self.session.execute(
            select(SubscriptionDevice)
            .options(selectinload(SubscriptionDevice.subscription))
            .where(SubscriptionDevice.id == device_id)
        )
        return result.scalar_one_or_none()

    async def get_by_subscription(self, subscription_id: int) -> list[SubscriptionDevice]:
        result = await self.session.execute(
            select(SubscriptionDevice)
            .where(SubscriptionDevice.subscription_id == subscription_id)
            .order_by(SubscriptionDevice.created_at)
        )
        return list(result.scalars().all())

    async def count_by_subscription(self, subscription_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(SubscriptionDevice)
            .where(SubscriptionDevice.subscription_id == subscription_id)
        )
        return result or 0

    async def create(self, device: SubscriptionDevice) -> SubscriptionDevice:
        self.session.add(device)
        await self.session.flush()
        return device

    async def delete(self, device: SubscriptionDevice) -> None:
        await self.session.delete(device)
        await self.session.flush()

    async def get_all_for_active_subscriptions(self) -> list[SubscriptionDevice]:
        result = await self.session.execute(
            select(SubscriptionDevice)
            .join(Subscription)
            .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .where(Subscription.expires_at > utcnow())
            .options(selectinload(SubscriptionDevice.subscription))
        )
        return list(result.scalars().all())


class DeviceService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.devices = DeviceRepository(session)

    async def ensure_default_device(self, subscription: Subscription) -> SubscriptionDevice:
        existing = await self.devices.get_by_subscription(subscription.id)
        if existing:
            return existing[0]

        device = SubscriptionDevice(
            subscription_id=subscription.id,
            client_uuid=subscription.client_uuid,
            name="Устройство 1",
        )
        return await self.devices.create(device)

    async def list_devices(self, subscription_id: int) -> list[SubscriptionDevice]:
        return await self.devices.get_by_subscription(subscription_id)

    async def add_device(self, subscription: Subscription) -> SubscriptionDevice:
        count = await self.devices.count_by_subscription(subscription.id)
        if count >= self.settings.max_devices_per_subscription:
            raise ValueError(
                f"Достигнут лимит устройств ({self.settings.max_devices_per_subscription})"
            )

        device = SubscriptionDevice(
            subscription_id=subscription.id,
            client_uuid=uuid_std.uuid4(),
            name=f"Устройство {count + 1}",
        )
        await self.devices.create(device)
        subscription.client_uuid = (
            await self.devices.get_by_subscription(subscription.id)
        )[0].client_uuid
        await self.session.flush()
        return device

    async def delete_device(
        self,
        device_id: int,
        subscription_id: int,
    ) -> bool:
        device = await self.devices.get_by_id(device_id)
        if not device or device.subscription_id != subscription_id:
            return False

        subscription = device.subscription
        await self.devices.delete(device)

        if subscription:
            remaining = await self.devices.get_by_subscription(subscription_id)
            if remaining:
                subscription.client_uuid = remaining[0].client_uuid
            await self.session.flush()
        return True

    @staticmethod
    def xray_email(user_id: int, device_id: int) -> str:
        from src.services.xray_sync import QOOQ_EMAIL_PREFIX

        return f"{QOOQ_EMAIL_PREFIX}{user_id}-d{device_id}"
