"""Load and apply VPN JSON config templates from the database."""

import copy
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.enums import VpnConfigType
from src.models import VpnConfig
from src.services.vpn_config import XRAY_CONFIG_TEMPLATE, sanitize_remark

PLACEHOLDER_UUID = "{uuid}"
PLACEHOLDER_REMARKS = "{remarks}"


def export_default_json_template() -> str:
    """Built-in Xray JSON with placeholders for admin seeding."""
    config = copy.deepcopy(XRAY_CONFIG_TEMPLATE)
    config["remarks"] = PLACEHOLDER_REMARKS
    config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = PLACEHOLDER_UUID
    return json.dumps(config, ensure_ascii=False, indent=2)


def validate_json_template(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON-конфиг должен быть объектом")
    if PLACEHOLDER_UUID not in raw:
        raise ValueError(f"Шаблон должен содержать плейсхолдер {PLACEHOLDER_UUID}")
    return data


def apply_json_template(
    template: dict[str, Any] | str,
    client_uuid: uuid.UUID,
    remark: str,
) -> dict[str, Any]:
    if isinstance(template, dict):
        raw = json.dumps(template, ensure_ascii=False)
    else:
        raw = template

    safe_remark = sanitize_remark(remark)
    filled = raw.replace(PLACEHOLDER_UUID, str(client_uuid)).replace(
        PLACEHOLDER_REMARKS, safe_remark
    )
    config = json.loads(filled)
    config["remarks"] = safe_remark
    return config


class VpnConfigStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_configs(self) -> list[VpnConfig]:
        result = await self.session.execute(
            select(VpnConfig)
            .options(selectinload(VpnConfig.server))
            .order_by(VpnConfig.server_id, VpnConfig.id)
        )
        return list(result.scalars().unique().all())

    async def get_by_id(self, config_id: int) -> VpnConfig | None:
        result = await self.session.execute(
            select(VpnConfig)
            .options(selectinload(VpnConfig.server))
            .where(VpnConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def resolve_profile_config(
        self,
        config_id: int | None = None,
    ) -> VpnConfig | None:
        config = None
        if config_id:
            config = await self.get_by_id(config_id)
            if config and (
                not config.is_active or config.config_type != VpnConfigType.XRAY_JSON
            ):
                config = None

        if not config:
            result = await self.session.execute(
                select(VpnConfig)
                .where(
                    VpnConfig.is_active.is_(True),
                    VpnConfig.config_type == VpnConfigType.XRAY_JSON,
                    VpnConfig.is_default.is_(True),
                )
                .limit(1)
            )
            config = result.scalar_one_or_none()

        if not config:
            result = await self.session.execute(
                select(VpnConfig)
                .where(
                    VpnConfig.is_active.is_(True),
                    VpnConfig.config_type == VpnConfigType.XRAY_JSON,
                )
                .order_by(VpnConfig.id)
                .limit(1)
            )
            config = result.scalar_one_or_none()

        return config

    async def get_profile_template(
        self,
        config_id: int | None = None,
    ) -> dict[str, Any] | None:
        config = await self.resolve_profile_config(config_id)
        if not config:
            return None

        try:
            return validate_json_template(config.config_template)
        except ValueError:
            return None

    async def create_config(
        self,
        server_id: int,
        name: str,
        config_type: VpnConfigType,
        config_template: str,
        is_default: bool = False,
    ) -> VpnConfig:
        if config_type == VpnConfigType.XRAY_JSON:
            validate_json_template(config_template)

        if is_default:
            await self._clear_default(config_type)

        config = VpnConfig(
            server_id=server_id,
            name=name.strip(),
            config_type=config_type,
            config_template=config_template.strip(),
            is_default=is_default,
            is_active=True,
        )
        self.session.add(config)
        await self.session.flush()
        return config

    async def update_config(
        self,
        config_id: int,
        *,
        name: str | None = None,
        config_template: str | None = None,
        is_default: bool | None = None,
        is_active: bool | None = None,
    ) -> VpnConfig | None:
        config = await self.get_by_id(config_id)
        if not config:
            return None

        if name is not None:
            config.name = name.strip()
        if config_template is not None:
            if config.config_type == VpnConfigType.XRAY_JSON:
                validate_json_template(config_template)
            config.config_template = config_template.strip()
        if is_default is not None:
            if is_default:
                await self._clear_default(config.config_type, exclude_id=config.id)
            config.is_default = is_default
        if is_active is not None:
            config.is_active = is_active

        await self.session.flush()
        return config

    async def delete_config(self, config_id: int) -> bool:
        from src.models import Subscription

        config = await self.get_by_id(config_id)
        if not config:
            return False

        linked = await self.session.scalar(
            select(Subscription.id)
            .where(Subscription.config_id == config_id)
            .limit(1)
        )
        if linked:
            raise ValueError("Нельзя удалить: конфиг привязан к подпискам")

        await self.session.delete(config)
        await self.session.flush()
        return True

    async def _clear_default(
        self,
        config_type: VpnConfigType,
        exclude_id: int | None = None,
    ) -> None:
        result = await self.session.execute(
            select(VpnConfig).where(
                VpnConfig.config_type == config_type,
                VpnConfig.is_default.is_(True),
            )
        )
        for item in result.scalars().all():
            if exclude_id and item.id == exclude_id:
                continue
            item.is_default = False
        await self.session.flush()

    async def seed_default_json_for_server(self, server_id: int) -> VpnConfig | None:
        result = await self.session.execute(
            select(VpnConfig).where(
                VpnConfig.server_id == server_id,
                VpnConfig.config_type == VpnConfigType.XRAY_JSON,
            )
        )
        if result.scalar_one_or_none():
            return None

        return await self.create_config(
            server_id=server_id,
            name="Xray JSON Profile",
            config_type=VpnConfigType.XRAY_JSON,
            config_template=export_default_json_template(),
            is_default=True,
        )
