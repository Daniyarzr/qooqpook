from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models import SystemSetting

REFERRAL_BONUS_KEY = "referral_bonus_percent"
REFERRAL_DISCOUNT_KEY = "referral_discount_percent"  # legacy
BOT_ADMIN_IDS_KEY = "bot_admin_telegram_ids"


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

    async def get_referral_bonus_percent(self) -> int:
        default = str(self.settings.referral_bonus_percent if self.settings else 10)
        raw = await self.get(REFERRAL_BONUS_KEY, None)
        if raw is None:
            raw = await self.get(REFERRAL_DISCOUNT_KEY, default)
        try:
            value = int(raw or default)
        except (TypeError, ValueError):
            value = int(default)
        return max(0, min(100, value))

    async def set_referral_bonus_percent(self, percent: int) -> int:
        percent = max(0, min(100, percent))
        await self.set(REFERRAL_BONUS_KEY, str(percent))
        return percent

    async def get_referral_discount_percent(self) -> int:
        return await self.get_referral_bonus_percent()

    async def set_referral_discount_percent(self, percent: int) -> int:
        return await self.set_referral_bonus_percent(percent)

    @staticmethod
    def _parse_id_list(raw: str | None) -> list[int]:
        if not raw:
            return []
        ids: list[int] = []
        for part in str(raw).split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    async def get_dynamic_bot_admin_ids(self) -> list[int]:
        raw = await self.get(BOT_ADMIN_IDS_KEY, "")
        return self._parse_id_list(raw)

    async def get_all_bot_admin_ids(self) -> list[int]:
        root = set(self.settings.admin_telegram_ids if self.settings else [])
        dynamic = set(await self.get_dynamic_bot_admin_ids())
        return sorted(root | dynamic)

    async def add_bot_admin_id(self, telegram_id: int) -> list[int]:
        dynamic = set(await self.get_dynamic_bot_admin_ids())
        dynamic.add(int(telegram_id))
        await self.set(BOT_ADMIN_IDS_KEY, ",".join(str(item) for item in sorted(dynamic)))
        return await self.get_all_bot_admin_ids()

    async def remove_bot_admin_id(self, telegram_id: int) -> list[int]:
        root = set(self.settings.admin_telegram_ids if self.settings else [])
        if int(telegram_id) in root:
            raise ValueError("Нельзя удалить главного админа из .env")
        dynamic = set(await self.get_dynamic_bot_admin_ids())
        dynamic.discard(int(telegram_id))
        await self.set(BOT_ADMIN_IDS_KEY, ",".join(str(item) for item in sorted(dynamic)))
        return await self.get_all_bot_admin_ids()
