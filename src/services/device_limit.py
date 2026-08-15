import logging
import re
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.enums import SubscriptionStatus, SuspensionReason
from src.core.utils import utcnow
from src.models import Subscription, SubscriptionHwid, User
from src.services.notifications import send_telegram_message

logger = logging.getLogger(__name__)

DEVICE_LIMIT_OVERFLOW_MESSAGE = """
⚠️ <b>Лимит устройств</b>

На одну подписку QooQ VPN — не более <b>{max_devices}</b> устройств.

✅ Первые {max_devices} устройства продолжают работать.
⛔ Новые устройства сверх лимита <b>не получат доступ</b>.

Чтобы освободить слот: бот → 📱 Моя подписка → 📱 Устройства → удалите лишнее.
"""

# Старый fallback fingerprint: sha256(ip:ua)[:32]
_PHANTOM_HWID_RE = re.compile(r"^[0-9a-f]{32}$")
_BROWSER_UA_RE = re.compile(r"mozilla/", re.IGNORECASE)
_CLIENT_UA_RE = re.compile(
    r"(happ|v2ray|v2rayng|v2raytun|clash|streisand|shadowrocket|sing-box|hiddify|nekobox)",
    re.IGNORECASE,
)


def extract_device_fingerprint(request: Request) -> tuple[str | None, str | None]:
    """Return (hwid, user_agent). hwid is None when client did not send a real device id.

    Never invent fingerprints from IP/UA — browser opens of /sub/ must not count as devices.
    """
    user_agent = request.headers.get("user-agent")
    for header in ("x-hwid", "X-HWID", "Hwid", "HTTP-X-HWID"):
        value = request.headers.get(header)
        if value and value.strip():
            return value.strip()[:128], user_agent
    return None, user_agent


def is_phantom_hwid(hwid: str, user_agent: str | None) -> bool:
    """Detect legacy IP:UA fallback rows and browser probes."""
    if _PHANTOM_HWID_RE.fullmatch(hwid or ""):
        return True
    ua = user_agent or ""
    if _BROWSER_UA_RE.search(ua) and not _CLIENT_UA_RE.search(ua):
        return True
    return False


def hwid_display_name(hwid: str, user_agent: str | None) -> str:
    ua = (user_agent or "").strip()
    lower = ua.casefold()
    if "happ/" in lower:
        if "/ios" in lower:
            return "📱 Happ · iOS"
        if "/android" in lower:
            return "📱 Happ · Android"
        if "/windows" in lower:
            return "💻 Happ · Windows"
        if "/macos" in lower or "/mac" in lower:
            return "💻 Happ · macOS"
        return "📱 Happ"
    if "v2raytun" in lower:
        return "📱 v2RayTun"
    if "v2rayng" in lower or "v2ray" in lower:
        return "📱 v2rayNG"
    if "shadowrocket" in lower:
        return "🚀 Shadowrocket"
    if "streisand" in lower:
        return "📱 Streisand"
    if "hiddify" in lower:
        return "📱 Hiddify"
    short = (hwid or "")[:12]
    return f"🔌 {short}…" if short else "🔌 Устройство"


class DeviceLimitService:
    SUSPENSION_REASON = SuspensionReason.DEVICE_LIMIT.value

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    @property
    def max_devices(self) -> int:
        return self.settings.max_devices_per_subscription

    async def list_hwids(self, subscription_id: int) -> list[SubscriptionHwid]:
        result = await self.session.execute(
            select(SubscriptionHwid)
            .where(SubscriptionHwid.subscription_id == subscription_id)
            .order_by(SubscriptionHwid.first_seen_at.asc(), SubscriptionHwid.id.asc())
        )
        return list(result.scalars().all())

    async def count_hwids(self, subscription_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(SubscriptionHwid)
            .where(SubscriptionHwid.subscription_id == subscription_id)
        )
        return result or 0

    async def allowed_hwid_set(self, subscription_id: int) -> set[str]:
        """Первые N устройств по дате первого входа — им доступ разрешён."""
        hwids = await self.list_hwids(subscription_id)
        return {entry.hwid for entry in hwids[: self.max_devices]}

    async def is_hwid_allowed(self, subscription_id: int, hwid: str) -> bool:
        return hwid in await self.allowed_hwid_set(subscription_id)

    async def purge_phantom_hwids(self, subscription_id: int | None = None) -> int:
        """Remove legacy fallback / browser fingerprints that inflated the limit."""
        stmt = select(SubscriptionHwid)
        if subscription_id is not None:
            stmt = stmt.where(SubscriptionHwid.subscription_id == subscription_id)
        result = await self.session.execute(stmt)
        removed = 0
        for entry in result.scalars().all():
            if is_phantom_hwid(entry.hwid, entry.user_agent):
                await self.session.delete(entry)
                removed += 1
        if removed:
            await self.session.flush()
            logger.info(
                "Purged %s phantom HWID(s)%s",
                removed,
                f" for subscription {subscription_id}" if subscription_id else "",
            )
        return removed

    async def prune_stale_hwids(
        self,
        subscription_id: int,
        *,
        idle_days: int = 30,
    ) -> int:
        """Drop HWIDs not seen for a long time so reinstalls don't permanently burn slots."""
        cutoff = utcnow() - timedelta(days=idle_days)
        result = await self.session.execute(
            select(SubscriptionHwid).where(
                SubscriptionHwid.subscription_id == subscription_id,
                SubscriptionHwid.last_seen_at < cutoff,
            )
        )
        entries = list(result.scalars().all())
        for entry in entries:
            await self.session.delete(entry)
        if entries:
            await self.session.flush()
        return len(entries)

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

    async def delete_hwid(self, subscription_id: int, hwid_id: int) -> bool:
        result = await self.session.execute(
            select(SubscriptionHwid).where(
                SubscriptionHwid.id == hwid_id,
                SubscriptionHwid.subscription_id == subscription_id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.flush()
        return True

    async def lift_legacy_device_limit_suspend(self, subscription: Subscription) -> bool:
        """Старая логика морозила всю подписку — снимаем, доступ режем по устройствам."""
        if subscription.status != SubscriptionStatus.SUSPENDED:
            return False
        if subscription.suspension_reason != self.SUSPENSION_REASON:
            return False

        subscription.status = (
            SubscriptionStatus.TRIAL if subscription.is_trial else SubscriptionStatus.ACTIVE
        )
        subscription.suspension_reason = None
        subscription.device_limit_notified_at = None
        await self.session.flush()

        from src.services import SubscriptionService
        from src.services.config_credentials import ConfigCredentialService

        await ConfigCredentialService(self.session, self.settings).ensure_credentials(
            subscription
        )
        await SubscriptionService(self.session, self.settings).sync_xray_clients()
        logger.info(
            "Lifted legacy device_limit suspend for subscription %s",
            subscription.id,
        )
        return True

    async def check_and_enforce(
        self,
        subscription: Subscription,
        user: User,
        request: Request,
    ) -> bool:
        """True = этому устройству отдаём inactive (сверх лимита).

        Подписку целиком не приостанавливаем: слоты 1..N работают, N+1.. — нет.
        """
        await self.purge_phantom_hwids(subscription.id)
        await self.prune_stale_hwids(subscription.id)

        if subscription.status == SubscriptionStatus.EXPIRED:
            return False

        if (
            subscription.status == SubscriptionStatus.SUSPENDED
            and subscription.suspension_reason == self.SUSPENSION_REASON
        ):
            await self.lift_legacy_device_limit_suspend(subscription)

        if subscription.status == SubscriptionStatus.SUSPENDED:
            return False

        hwid, user_agent = extract_device_fingerprint(request)
        if not hwid:
            # Браузер / curl без x-hwid — не считаем слотом
            return False

        await self.record_hwid(subscription.id, hwid, user_agent)
        allowed = await self.is_hwid_allowed(subscription.id, hwid)
        if allowed:
            return False

        await self._notify_overflow_once(subscription, user)
        logger.info(
            "Device over limit for sub %s user %s hwid=%s…",
            subscription.id,
            user.id,
            hwid[:12],
        )
        return True

    async def _notify_overflow_once(self, subscription: Subscription, user: User) -> None:
        if subscription.device_limit_notified_at:
            return
        text = DEVICE_LIMIT_OVERFLOW_MESSAGE.format(max_devices=self.max_devices)
        sent = await send_telegram_message(self.settings, user.telegram_id, text)
        if sent:
            subscription.device_limit_notified_at = utcnow()
            await self.session.flush()

    async def suspend_for_device_limit(self, subscription: Subscription, user: User) -> bool:
        """Устарело: глобальная заморозка больше не используется."""
        logger.warning(
            "suspend_for_device_limit called for sub %s — ignored (soft per-device limit)",
            subscription.id,
        )
        return False

    async def try_reactivate(
        self,
        subscription: Subscription,
        *,
        clear_hwids: bool = True,
    ) -> bool:
        """Совместимость: снимает только legacy SUSPENDED/device_limit."""
        if subscription.suspension_reason != self.SUSPENSION_REASON:
            return False
        if subscription.status != SubscriptionStatus.SUSPENDED:
            return False

        await self.purge_phantom_hwids(subscription.id)
        await self.prune_stale_hwids(subscription.id)

        if clear_hwids:
            await self.clear_hwids(subscription.id)

        return await self.lift_legacy_device_limit_suspend(subscription)

    async def clear_hwids(self, subscription_id: int) -> int:
        result = await self.session.execute(
            delete(SubscriptionHwid).where(SubscriptionHwid.subscription_id == subscription_id)
        )
        await self.session.flush()
        return result.rowcount or 0
