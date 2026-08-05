from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, subscription_menu
from src.bot.texts.messages import (
    EXTEND_INSUFFICIENT_BALANCE,
    EXTEND_SUCCESS,
    PLANS_HEADER,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_EXPIRED,
    SUBSCRIPTION_NONE,
    TRIAL_ACTIVATED,
    TRIAL_ALREADY_USED,
)
from src.core.config import Settings
from src.core.utils import build_subscription_url, format_datetime_ru, format_duration_until
from src.models import User
from src.repositories import PlanRepository, UserRepository
from src.services import SubscriptionService

router = Router(name="subscription")


@router.callback_query(F.data == "sub:status")
async def subscription_status(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    service = SubscriptionService(session, settings)
    sub = await service.get_user_subscription(user.id)

    if sub:
        sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
        text = SUBSCRIPTION_ACTIVE.format(
            expires_at=format_datetime_ru(sub.expires_at),
            duration=format_duration_until(sub.expires_at),
            subscription_url=sub_url,
        )
        has_sub = True
    else:
        expired_subs = await service.subscriptions.get_active_by_user(user.id)
        text = SUBSCRIPTION_NONE
        has_sub = False

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=subscription_menu(has_sub, user.trial_used),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:trial")
async def activate_trial(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    if user.trial_used:
        await callback.message.edit_text(
            TRIAL_ALREADY_USED,
            parse_mode="HTML",
            reply_markup=back_to_menu(),
        )
        await callback.answer()
        return

    service = SubscriptionService(session, settings)
    try:
        sub = await service.activate_trial(user.id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
    text = TRIAL_ACTIVATED.format(
        days=settings.trial_days,
        expires_at=format_datetime_ru(sub.expires_at),
        subscription_url=sub_url,
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer("🎁 Пробный период активирован!")


@router.callback_query(F.data == "sub:plans")
async def show_plans(callback: CallbackQuery, session: AsyncSession):
    repo = PlanRepository(session)
    plans = await repo.get_active_plans()

    if not plans:
        await callback.answer("Тарифы пока не настроены", show_alert=True)
        return

    from src.bot.keyboards.inline import plans_keyboard

    await callback.message.edit_text(
        PLANS_HEADER,
        parse_mode="HTML",
        reply_markup=plans_keyboard(plans),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:buy:"))
async def confirm_purchase(callback: CallbackQuery, session: AsyncSession):
    plan_id = int(callback.data.split(":")[2])
    repo = PlanRepository(session)
    plan = await repo.get_by_id(plan_id)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    from src.bot.keyboards.inline import confirm_purchase as confirm_kb

    text = f"💎 <b>{plan.name}</b>\n\n📅 {plan.days} дней\n💰 Стоимость: <b>{plan.price} ₽</b>"
    if plan.description:
        text += f"\n\n{plan.description}"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_kb(plan.id, plan.name, plan.price),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:confirm:"))
async def process_purchase(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    plan_id = int(callback.data.split(":")[2])
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    plan_repo = PlanRepository(session)
    plan = await plan_repo.get_by_id(plan_id)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    if user.balance < plan.price:
        text = EXTEND_INSUFFICIENT_BALANCE.format(balance=user.balance, price=plan.price)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
        await callback.answer()
        return

    service = SubscriptionService(session, settings)
    try:
        sub = await service.extend_subscription(user.id, plan.id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
    text = EXTEND_SUCCESS.format(
        expires_at=format_datetime_ru(sub.expires_at),
        duration=format_duration_until(sub.expires_at),
        subscription_url=sub_url,
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer("✅ Подписка оформлена!")
