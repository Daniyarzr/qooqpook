from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, balance_menu
from src.bot.texts.messages import BALANCE, BALANCE_HISTORY_HEADER, BALANCE_HISTORY_ITEM, HELP, PROFILE, REFERRAL
from src.core.config import Settings
from src.core.enums import TransactionType
from src.core.utils import build_referral_link, format_datetime_ru
from src.models import ReferralReward, User
from src.repositories import UserRepository
from src.services import BalanceService

router = Router(name="profile")


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    result = await session.execute(
        select(func.count()).select_from(User).where(User.referred_by_id == user.id)
    )
    referrals_count = result.scalar() or 0

    text = PROFILE.format(
        telegram_id=user.telegram_id,
        uuid=str(user.client_uuid),
        balance=user.balance,
        referral_code=user.referral_code,
        referrals_count=referrals_count,
        created_at=format_datetime_ru(user.created_at),
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    text = BALANCE.format(balance=user.balance)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=balance_menu())
    await callback.answer()


@router.callback_query(F.data == "balance:history")
async def show_balance_history(callback: CallbackQuery, session: AsyncSession):
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

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=balance_menu())
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

    earned_result = await session.execute(
        select(func.coalesce(func.sum(ReferralReward.bonus_amount), 0)).where(
            ReferralReward.referrer_id == user.id
        )
    )
    earned = earned_result.scalar() or 0

    referral_link = build_referral_link(settings.bot_username, user.referral_code)
    text = REFERRAL.format(
        referral_link=referral_link,
        bonus_percent=settings.referral_bonus_percent,
        bonus_days=settings.referral_bonus_days,
        referrals_count=referrals_count,
        earned=earned,
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()
