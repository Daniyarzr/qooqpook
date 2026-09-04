from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, balance_menu
from src.bot.texts.messages import BALANCE, BALANCE_HISTORY_HEADER, BALANCE_HISTORY_ITEM, HELP, PROFILE, REFERRAL
from src.core.config import Settings
from src.core.enums import SubscriptionStatus, TransactionType
from src.core.utils import (
    build_referral_link,
    format_datetime_ru,
    utcnow,
)
from src.models import User
from src.repositories import UserRepository
from src.services import BalanceService, SubscriptionService
from src.services.referral import ReferralService
from src.services.system_settings import SystemSettingsService

router = Router(name="profile")


def _profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="🎁 Рефералы", callback_data="referral"),
            ],
            [InlineKeyboardButton(text="📱 Подписка", callback_data="sub:status")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
        ]
    )


def _subscription_line(subscription, settings: Settings, device_count: int) -> str:
    if not subscription:
        return "нет подписки"

    if subscription.status == SubscriptionStatus.SUSPENDED:
        return "приостановлена"

    if subscription.status == SubscriptionStatus.EXPIRED or (
        subscription.expires_at and subscription.expires_at <= utcnow()
    ):
        return "истекла"

    label = "trial" if subscription.is_trial else "активна"
    shown = min(device_count, settings.max_devices_per_subscription)
    return (
        f"{label} до <b>{format_datetime_ru(subscription.expires_at)}</b> "
        f"· {shown}/{settings.max_devices_per_subscription} устр."
    )


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    result = await session.execute(
        select(func.count()).select_from(User).where(User.referred_by_id == user.id)
    )
    referrals_count = result.scalar() or 0

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    device_count = 0
    if subscription:
        from src.services.device_limit import DeviceLimitService

        limit_service = DeviceLimitService(session, settings)
        await limit_service.purge_phantom_hwids(subscription.id)
        device_count = await limit_service.count_hwids(subscription.id)

    display_name = user.first_name or user.username or "Пользователь"
    username_suffix = f" · @{user.username}" if user.username else ""

    text = PROFILE.format(
        display_name=display_name,
        username_suffix=username_suffix,
        telegram_id=user.telegram_id,
        balance=user.balance,
        referral_code=user.referral_code,
        referrals_count=referrals_count,
        created_at=format_datetime_ru(user.created_at),
        subscription_line=_subscription_line(subscription, settings, device_count),
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_profile_keyboard())
    await callback.answer()


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    text = BALANCE.format(balance=user.balance)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=balance_menu(settings.yookassa_enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "balance:history")
async def show_balance_history(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    service = BalanceService(session)
    transactions = await service.get_history(user.id, limit=10)

    text = BALANCE_HISTORY_HEADER
    if not transactions:
        text += "Пока нет операций."
    else:
        emoji_map = {
            TransactionType.DEPOSIT: "💚",
            TransactionType.WITHDRAWAL: "🔴",
            TransactionType.SUBSCRIPTION_PAYMENT: "💎",
            TransactionType.REFERRAL_BONUS: "🎁",
            TransactionType.ADMIN_ADJUSTMENT: "⚙️",
        }
        for tx in transactions:
            emoji = emoji_map.get(tx.type, "📝")
            sign = "+" if tx.amount > 0 else ""
            text += BALANCE_HISTORY_ITEM.format(
                emoji=emoji,
                amount=f"{sign}{tx.amount}",
                description=tx.description or tx.type.value,
                date=format_datetime_ru(tx.created_at),
            )

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=balance_menu(settings.yookassa_enabled)
    )
    await callback.answer()


@router.callback_query(F.data == "referral")
async def show_referral(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    result = await session.execute(
        select(func.count()).select_from(User).where(User.referred_by_id == user.id)
    )
    referrals_count = result.scalar() or 0

    settings_service = SystemSettingsService(session, settings)
    referral_service = ReferralService(session, settings)
    bonus_percent = await settings_service.get_referral_bonus_percent()
    total_earned = await referral_service.total_bonus_earned(user.id)

    referral_link = build_referral_link(settings.bot_username, user.telegram_id)
    text = REFERRAL.format(
        referral_link=referral_link,
        bonus_percent=bonus_percent,
        referrals_count=referrals_count,
        total_earned=total_earned,
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery, settings: Settings):
    text = HELP.format(support_username=settings.support_username.lstrip("@"))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "connect:guide")
async def show_connect_guide(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
):
    text = await SystemSettingsService(session, settings).get_connect_guide_text()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()
