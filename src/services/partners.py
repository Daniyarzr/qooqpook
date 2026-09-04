"""Partner acquisition links — admin-created, separate from user referrals."""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import TransactionType
from src.core.utils import utcnow
from src.models import PartnerLink, Transaction, User

# Readable short codes (no ambiguous 0/O/1/I/l)
_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_CODE_RE = re.compile(r"^[a-z0-9]{3,16}$")


def normalize_partner_code(raw: str) -> str:
    return raw.strip().lower()


def generate_partner_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def normalize_telegram_username(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lstrip("@")
    return value or None


def build_partner_short_url(hub_domain: str, code: str) -> str:
    return f"https://{hub_domain}/p/{code}"


def build_partner_bot_start(bot_username: str, code: str) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start=p_{code}"


@dataclass
class PartnerStats:
    clicks: int
    registrations: int
    buyers: int
    revenue: Decimal
    conversion_pct: float


class PartnerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str, *, active_only: bool = False) -> PartnerLink | None:
        normalized = normalize_partner_code(code)
        if not normalized:
            return None
        query = select(PartnerLink).where(PartnerLink.code == normalized)
        if active_only:
            query = query.where(PartnerLink.is_active.is_(True))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, link_id: int) -> PartnerLink | None:
        result = await self.session.execute(select(PartnerLink).where(PartnerLink.id == link_id))
        return result.scalar_one_or_none()

    async def list_links(self) -> list[PartnerLink]:
        result = await self.session.execute(
            select(PartnerLink).order_by(PartnerLink.created_at.desc(), PartnerLink.id.desc())
        )
        return list(result.scalars().all())

    async def _ensure_unique_code(self, preferred: str | None = None) -> str:
        if preferred:
            code = normalize_partner_code(preferred)
            if not _CODE_RE.match(code):
                raise ValueError("Код: 3–16 символов, только латиница и цифры")
            existing = await self.get_by_code(code)
            if existing:
                raise ValueError("Такой код уже занят")
            return code

        for _ in range(20):
            code = generate_partner_code()
            if not await self.get_by_code(code):
                return code
        raise ValueError("Не удалось сгенерировать уникальный код")

    async def create_link(
        self,
        *,
        name: str,
        telegram_username: str | None = None,
        note: str | None = None,
        code: str | None = None,
    ) -> PartnerLink:
        name = name.strip()
        if not name:
            raise ValueError("Укажите название партнёра")
        if len(name) > 128:
            raise ValueError("Название слишком длинное")

        link = PartnerLink(
            code=await self._ensure_unique_code(code),
            name=name,
            telegram_username=normalize_telegram_username(telegram_username),
            note=(note or "").strip() or None,
            click_count=0,
            is_active=True,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def toggle_active(self, link_id: int) -> PartnerLink | None:
        link = await self.get_by_id(link_id)
        if not link:
            return None
        link.is_active = not link.is_active
        link.updated_at = utcnow()
        await self.session.flush()
        return link

    async def delete_link(self, link_id: int) -> bool:
        link = await self.get_by_id(link_id)
        if not link:
            return False
        regs = await self.session.scalar(
            select(func.count()).select_from(User).where(User.partner_link_id == link_id)
        )
        if regs and regs > 0:
            raise ValueError("Нельзя удалить: уже есть регистрации по ссылке. Выключите её.")
        await self.session.delete(link)
        await self.session.flush()
        return True

    async def record_click(self, code: str) -> PartnerLink | None:
        link = await self.get_by_code(code, active_only=True)
        if not link:
            return None
        link.click_count = int(link.click_count or 0) + 1
        link.updated_at = utcnow()
        await self.session.flush()
        return link

    async def stats_for(self, link_id: int) -> PartnerStats:
        registrations = int(
            await self.session.scalar(
                select(func.count()).select_from(User).where(User.partner_link_id == link_id)
            )
            or 0
        )
        buyers = int(
            await self.session.scalar(
                select(func.count(func.distinct(Transaction.user_id)))
                .select_from(Transaction)
                .join(User, User.id == Transaction.user_id)
                .where(
                    User.partner_link_id == link_id,
                    Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT,
                )
            )
            or 0
        )
        revenue = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .select_from(Transaction)
            .join(User, User.id == Transaction.user_id)
            .where(
                User.partner_link_id == link_id,
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT,
            )
        )
        revenue_dec = Decimal(str(revenue or 0))
        link = await self.get_by_id(link_id)
        clicks = int(link.click_count if link else 0)
        conversion = (registrations / clicks * 100.0) if clicks else 0.0
        return PartnerStats(
            clicks=clicks,
            registrations=registrations,
            buyers=buyers,
            revenue=revenue_dec,
            conversion_pct=round(conversion, 1),
        )

    async def list_with_stats(self) -> list[dict]:
        links = await self.list_links()
        rows: list[dict] = []
        for link in links:
            stats = await self.stats_for(link.id)
            rows.append({"link": link, "stats": stats})
        return rows

    async def list_users(self, link_id: int, *, limit: int = 100) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.partner_link_id == link_id)
            .order_by(User.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
