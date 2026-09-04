import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_subscription_token() -> str:
    return secrets.token_urlsafe(32)


def extend_expiry(current_expires_at: datetime, days: int) -> datetime:
    """Extend subscription: from current expiry if still active, else from now."""
    now = utcnow()
    base = current_expires_at if current_expires_at > now else now
    return base + timedelta(days=days)


def build_subscription_url(hub_domain: str, token: str) -> str:
    return f"https://{hub_domain}/sub/{token}"


def build_referral_link(bot_username: str, telegram_id: int) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start=ref_{telegram_id}"


def generate_partner_code(length: int = 6) -> str:
    """Short readable partner codes (no ambiguous chars)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_partner_short_url(hub_domain: str, code: str) -> str:
    return f"https://{hub_domain}/p/{code}"


def build_partner_bot_start(bot_username: str, code: str) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start=p_{code}"


def build_telegram_link(username: str) -> str:
    return f"https://t.me/{username.lstrip('@')}"


def support_telegram_link(support_username: str) -> str:
    return build_telegram_link(support_username)


def format_duration_until(expires_at: datetime) -> str:
    now = utcnow()
    if expires_at <= now:
        return "истекла"

    delta = expires_at - now
    days = delta.days
    hours = delta.seconds // 3600

    if days > 0:
        return f"{days} дн. {hours} ч."
    if hours > 0:
        return f"{hours} ч."
    minutes = delta.seconds // 60
    return f"{minutes} мин."


def format_datetime_ru(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 2)


def format_bytes(value: int) -> str:
    if value >= 1024**3:
        return f"{bytes_to_gb(value):.2f} GB"
    if value >= 1024**2:
        return f"{value / (1024**2):.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} B"
