from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import SystemSetting

REFERRAL_DISCOUNT_KEY = "referral_discount_percent"


class SystemSettingsService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self.session = session
        self.settings = settings

    async def get(self, key: str, default: str | None = None) -> str | None:
        result = await self.session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            return row.value
        return default

    async def set(self, key: str, value: str) -> SystemSetting:
        result = await self.session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            await self.session.flush()
            return row
        row = SystemSetting(key=key, value=value)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_referral_discount_percent(self) -> int:
        default = str(self.settings.referral_discount_percent if self.settings else 10)
        raw = await self.get(REFERRAL_DISCOUNT_KEY, default)
        try:
            value = int(raw or default)
        except (TypeError, ValueError):
            value = int(default)
        return max(0, min(100, value))

    async def set_referral_discount_percent(self, percent: int) -> int:
        percent = max(0, min(100, percent))
        await self.set(REFERRAL_DISCOUNT_KEY, str(percent))
        return percent
