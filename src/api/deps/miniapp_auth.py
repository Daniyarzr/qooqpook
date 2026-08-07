from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.telegram_webapp import TelegramWebAppError, validate_init_data
from src.db.session import get_session
from src.models import User
from src.repositories import UserRepository


async def get_miniapp_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    try:
        auth = validate_init_data(x_telegram_init_data, settings.bot_token)
    except TelegramWebAppError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(auth.user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered")

    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")

    return user


async def _sync_telegram_profile(user: User, tg_user, session: AsyncSession) -> User:
    changed = False
    for field, value in (
        ("username", tg_user.username),
        ("first_name", tg_user.first_name),
        ("last_name", tg_user.last_name),
    ):
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed = True
    if changed:
        await session.flush()
    return user


async def get_or_create_miniapp_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> tuple[User, bool]:
    try:
        auth = validate_init_data(x_telegram_init_data, settings.bot_token)
    except TelegramWebAppError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(auth.user.id)
    if user:
        if user.is_banned:
            raise HTTPException(status_code=403, detail="User is banned")
        user = await _sync_telegram_profile(user, auth.user, session)
        return user, False

    referred_by_id = None
    start_param = auth.start_param or ""
    if start_param.startswith("ref_"):
        referrer = await repo.get_by_referral_code(start_param[4:])
        if referrer:
            referred_by_id = referrer.id

    user = await repo.create(
        telegram_id=auth.user.id,
        username=auth.user.username,
        first_name=auth.user.first_name,
        last_name=auth.user.last_name,
        referred_by_id=referred_by_id,
    )
    return user, bool(referred_by_id)
