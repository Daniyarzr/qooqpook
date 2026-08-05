from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, balance_menu
from src.bot.texts.messages import BALANCE, BALANCE_HISTORY_HEADER, BALANCE_HISTORY_ITEM, HELP, PROFILE, REFERRAL
from src.core.config import Settings
from src.core.enums import TransactionType
from src.core.utils import build_referral_link, format_datetime_ru
from src.repositories import UserRepository
from src.services import BalanceService, SubscriptionService
from src.services.devices import DeviceService
from src.services.system_settings import SystemSettingsService

router = Router(name="profile")


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
    subscription = await sub_service.get_user_subscription(user.id)
    subscription_uuid = "—"
    if subscription:
        device_service = DeviceService(session, settings)
        devices = await device_service.list_devices(subscription.id)
        if devices:
            subscription_uuid = str(devices[0].client_uuid)
        else:
            subscription_uuid = str(subscription.client_uuid)

    text = PROFILE.format(
        telegram_id=user.telegram_id,
        uuid=subscription_uuid,
        balance=user.balance,
        referral_code=user.referral_code,
        referrals_count=referrals_count,
        created_at=format_datetime_ru(user.created_at),
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
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
    discount_percent = await settings_service.get_referral_discount_percent()
    welcome = bool(user.referred_by_id and not user.referral_discount_used)
    current_discount = min(
        100,
        referrals_count * discount_percent + (discount_percent if welcome else 0),
    )

    referral_link = build_referral_link(settings.bot_username, user.referral_code)
    text = REFERRAL.format(
        referral_link=referral_link,
        discount_percent=discount_percent,
        referrals_count=referrals_count,
        current_discount=current_discount,
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()
