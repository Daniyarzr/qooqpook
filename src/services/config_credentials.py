"""Per-config UUID credentials for subscriptions."""

from __future__ import annotations

import logging
import uuid as uuid_std

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import Settings
from src.core.enums import SubscriptionStatus, VpnConfigType
from src.core.utils import utcnow
from src.models import Subscription, SubscriptionConfigCredential, SubscriptionDevice, VpnConfig, VpnServer

logger = logging.getLogger(__name__)


class ConfigCredentialService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self.session = session
        self.settings = settings

    async def resolve_server_id(self, subscription: Subscription) -> int | None:
        if subscription.config_id and subscription.config:
            return subscription.config.server_id
        if subscription.config_id:
            result = await self.session.execute(
                select(VpnConfig.server_id).where(VpnConfig.id == subscription.config_id)
            )
            server_id = result.scalar_one_or_none()
            if server_id:
                return server_id

        result = await self.session.execute(
            select(VpnServer.id)
            .where(VpnServer.is_active.is_(True))
            .order_by(VpnServer.sort_order, VpnServer.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_server_configs(self, server_id: int) -> list[VpnConfig]:
        result = await self.session.execute(
            select(VpnConfig)
            .where(
                VpnConfig.server_id == server_id,
                VpnConfig.is_active.is_(True),
            )
            .order_by(VpnConfig.id)
        )
        return list(result.scalars().all())

    async def ensure_credentials(self, subscription: Subscription) -> list[SubscriptionConfigCredential]:
        from src.services.devices import DeviceService

        server_id = await self.resolve_server_id(subscription)
        if not server_id:
            return []

        if self.settings:
            device_service = DeviceService(self.session, self.settings)
            devices = await device_service.list_devices(subscription.id)
            if not devices:
                devices = [await device_service.ensure_default_device(subscription)]
        else:
            devices = list(subscription.devices) if subscription.devices else []

        configs = await self.list_server_configs(server_id)
        if not configs:
            return []

        existing_result = await self.session.execute(
            select(SubscriptionConfigCredential)
            .options(
                selectinload(SubscriptionConfigCredential.device),
                selectinload(SubscriptionConfigCredential.vpn_config),
            )
            .where(
                SubscriptionConfigCredential.subscription_id == subscription.id,
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
        )
        existing = {
            (item.device_id, item.vpn_config_id): item
            for item in existing_result.scalars().all()
        }

        created: list[SubscriptionConfigCredential] = []
        for device in devices:
            for config in configs:
                key = (device.id, config.id)
                if key in existing:
                    continue
                credential = SubscriptionConfigCredential(
                    subscription_id=subscription.id,
                    device_id=device.id,
                    vpn_config_id=config.id,
                    client_uuid=uuid_std.uuid4(),
                )
                self.session.add(credential)
                created.append(credential)
                existing[key] = credential

        if created:
            await self.session.flush()
            logger.info(
                "Created %s config credentials for subscription %s",
                len(created),
                subscription.id,
            )
        return list(existing.values())

    async def list_active(
        self,
        subscription_id: int,
        *,
        config_type: VpnConfigType | None = None,
        vpn_config_id: int | None = None,
    ) -> list[SubscriptionConfigCredential]:
        query = (
            select(SubscriptionConfigCredential)
            .options(
                selectinload(SubscriptionConfigCredential.device),
                selectinload(SubscriptionConfigCredential.vpn_config),
            )
            .where(
                SubscriptionConfigCredential.subscription_id == subscription_id,
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
            .order_by(
                SubscriptionConfigCredential.device_id,
                SubscriptionConfigCredential.vpn_config_id,
            )
        )
        if vpn_config_id is not None:
            query = query.where(SubscriptionConfigCredential.vpn_config_id == vpn_config_id)
        if config_type is not None:
            query = query.join(VpnConfig).where(VpnConfig.config_type == config_type)

        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_credential(
        self,
        subscription: Subscription,
        device_id: int,
        vpn_config_id: int,
    ) -> SubscriptionConfigCredential | None:
        await self.ensure_credentials(subscription)
        result = await self.session.execute(
            select(SubscriptionConfigCredential).where(
                SubscriptionConfigCredential.subscription_id == subscription.id,
                SubscriptionConfigCredential.device_id == device_id,
                SubscriptionConfigCredential.vpn_config_id == vpn_config_id,
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_subscription(self, subscription_id: int) -> int:
        result = await self.session.execute(
            select(SubscriptionConfigCredential).where(
                SubscriptionConfigCredential.subscription_id == subscription_id,
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
        )
        credentials = list(result.scalars().all())
        now = utcnow()
        for credential in credentials:
            credential.revoked_at = now
        if credentials:
            await self.session.flush()
            logger.info(
                "Revoked %s config credentials for subscription %s",
                len(credentials),
                subscription_id,
            )
        return len(credentials)

    async def refresh_subscription(self, subscription: Subscription) -> list[SubscriptionConfigCredential]:
        await self.revoke_subscription(subscription.id)
        return await self.ensure_credentials(subscription)

    async def revoke_device(self, device_id: int) -> int:
        result = await self.session.execute(
            select(SubscriptionConfigCredential).where(
                SubscriptionConfigCredential.device_id == device_id,
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
        )
        credentials = list(result.scalars().all())
        now = utcnow()
        for credential in credentials:
            credential.revoked_at = now
        if credentials:
            await self.session.flush()
        return len(credentials)

    async def get_all_for_active_subscriptions(self) -> list[SubscriptionConfigCredential]:
        result = await self.session.execute(
            select(SubscriptionConfigCredential)
            .join(Subscription)
            .where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                Subscription.expires_at > utcnow(),
                SubscriptionConfigCredential.revoked_at.is_(None),
            )
            .options(
                selectinload(SubscriptionConfigCredential.subscription),
                selectinload(SubscriptionConfigCredential.vpn_config),
            )
        )
        return list(result.scalars().unique().all())

    async def credential_device_map(
        self,
        subscription_ids: list[int] | None = None,
    ) -> dict[int, int]:
        query = select(
            SubscriptionConfigCredential.id,
            SubscriptionConfigCredential.device_id,
        ).where(SubscriptionConfigCredential.revoked_at.is_(None))
        if subscription_ids:
            query = query.where(
                SubscriptionConfigCredential.subscription_id.in_(subscription_ids)
            )
        result = await self.session.execute(query)
        return {row[0]: row[1] for row in result.all()}
