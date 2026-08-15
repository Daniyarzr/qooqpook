from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, subscription_menu
from src.bot.states import PromoStates
from src.bot.texts.messages import (
    EXTEND_INSUFFICIENT_BALANCE,
    EXTEND_SUCCESS,
    PLANS_HEADER,
    PROMO_APPLIED,
    PROMO_ASK,
    PROMO_INVALID,
    PURCHASE_PAYMENT_CREATED,
    PURCHASE_PAYMENT_SUCCESS,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_NONE,
    SUBSCRIPTION_RESET_CONFIRM,
    SUBSCRIPTION_RESET_SUCCESS,
    SUBSCRIPTION_SUSPENDED_DEVICES,
    TRIAL_ACTIVATED,
    TRIAL_ALREADY_USED,
)
from src.core.config import Settings
from src.core.enums import PaymentMethod, PaymentStatus, SubscriptionStatus, SuspensionReason
from src.core.utils import build_subscription_url, format_datetime_ru, format_duration_until
from src.repositories import PlanRepository, UserRepository
from src.services import SubscriptionService
from src.services.payment import PaymentService
from src.services.pricing import PurchasePricingService
from src.services.promo import PromoCodeService

router = Router(name="subscription")


def _parse_confirm_callback(data: str) -> tuple[int, int | None]:
    parts = data.split(":")
    plan_id = int(parts[2])
    promo_id = int(parts[3]) if len(parts) > 3 else None
    return plan_id, promo_id


async def _build_confirm_text(plan, promo=None) -> str:
    text = f"💎 <b>{plan.name}</b>\n\n📅 {plan.days} дней\n💰 Стоимость: <b>{plan.price} ₽</b>"

    if promo:
        text += (
            f"\n🎟 Промокод <code>{promo.promo.code}</code>: "
            f"<b>−{promo.discount_amount} ₽</b>"
        )
        text += f"\n💳 К оплате: <b>{promo.final_price} ₽</b>"

    if plan.description:
        text += f"\n\n{plan.description}"
    return text


async def _resolve_display_pricing(session, settings, user_id, plan, promo_id=None):
    return await PurchasePricingService(session, settings).resolve(user_id, plan, promo_id)


@router.callback_query(F.data == "sub:status")
async def subscription_status(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    service = SubscriptionService(session, settings)
    sub = await service.subscriptions.get_current_by_user(user.id)

    if sub and sub.status == SubscriptionStatus.SUSPENDED:
        if sub.suspension_reason == SuspensionReason.DEVICE_LIMIT.value:
            from src.services.device_limit import DeviceLimitService

            # Больше не морозим всю подписку — снимаем старую блокировку
            await DeviceLimitService(session, settings).lift_legacy_device_limit_suspend(sub)
            sub = await service.subscriptions.get_current_by_user(user.id)
        else:
            from src.bot.texts.messages import SUBSCRIPTION_SUSPENDED

            await callback.message.edit_text(
                SUBSCRIPTION_SUSPENDED,
                parse_mode="HTML",
                reply_markup=back_to_menu(),
            )
            await callback.answer()
            return

    sub = await service.get_user_subscription(user.id)

    if sub:
        sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
        from src.services.device_limit import DeviceLimitService

        limit_service = DeviceLimitService(session, settings)
        await limit_service.purge_phantom_hwids(sub.id)
        device_count = await limit_service.count_hwids(sub.id)
        text = SUBSCRIPTION_ACTIVE.format(
            expires_at=format_datetime_ru(sub.expires_at),
            duration=format_duration_until(sub.expires_at),
            subscription_url=sub_url,
            device_count=min(device_count, settings.max_devices_per_subscription),
            max_devices=settings.max_devices_per_subscription,
        )
        if device_count > settings.max_devices_per_subscription:
            text += (
                f"\n\n⚠️ Подключено устройств: <b>{device_count}</b>. "
                f"Сверх лимита доступ только у первых {settings.max_devices_per_subscription}."
            )
        has_sub = True
    else:
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
async def confirm_purchase(
    callback: CallbackQuery, session: AsyncSession, settings: Settings, state: FSMContext
):
    await state.clear()
    plan_id = int(callback.data.split(":")[2])
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    plan = await PlanRepository(session).get_by_id(plan_id)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    from src.bot.keyboards.inline import confirm_purchase as confirm_kb

    pricing = await _resolve_display_pricing(session, settings, user.id, plan)
    text = await _build_confirm_text(plan, promo=pricing.promo)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_kb(
            plan.id,
            plan.name,
            plan.price,
            promo_id=pricing.promo.promo.id if pricing.promo else None,
            final_price=pricing.final_price,
            balance=user.balance,
            yookassa_enabled=settings.yookassa_enabled,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:promo:"))
async def ask_promo_code(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    plan_id = int(callback.data.split(":")[2])
    repo = PlanRepository(session)
    plan = await repo.get_by_id(plan_id)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await state.set_state(PromoStates.waiting_code)
    await state.update_data(plan_id=plan_id)

    from src.bot.keyboards.inline import InlineKeyboardButton, InlineKeyboardMarkup

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"sub:buy:{plan_id}")],
        ]
    )
    await callback.message.edit_text(
        PROMO_ASK.format(plan_name=plan.name, price=plan.price),
        parse_mode="HTML",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@router.message(PromoStates.waiting_code)
async def apply_promo_code(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
):
    data = await state.get_data()
    plan_id = data.get("plan_id")
    if not plan_id:
        await state.clear()
        return

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        await state.clear()
        return

    plan_repo = PlanRepository(session)
    plan = await plan_repo.get_by_id(plan_id)
    if not plan:
        await message.answer("Тариф не найден")
        await state.clear()
        return

    code = (message.text or "").strip()
    if not code:
        await message.answer("Введите промокод текстом")
        return

    promo_service = PromoCodeService(session)
    try:
        promo_validation = await promo_service.validate(code, user.id, plan)
    except ValueError as exc:
        await message.answer(PROMO_INVALID.format(error=str(exc)))
        return

    pricing = await _resolve_display_pricing(
        session, settings, user.id, plan, promo_validation.promo.id
    )

    await state.clear()

    from src.bot.keyboards.inline import confirm_purchase as confirm_kb

    if pricing.promo:
        await message.answer(
            PROMO_APPLIED.format(
                code=pricing.promo.promo.code,
                discount=pricing.promo.discount_amount,
                final_price=pricing.final_price,
            ),
            parse_mode="HTML",
        )
    text = await _build_confirm_text(
        plan,
        promo=pricing.promo,
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=confirm_kb(
            plan.id,
            plan.name,
            plan.price,
            promo_id=pricing.promo.promo.id if pricing.promo else None,
            final_price=pricing.final_price,
            balance=user.balance,
            yookassa_enabled=settings.yookassa_enabled,
        ),
    )


@router.callback_query(F.data.startswith("sub:confirm:"))
async def process_purchase_balance(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    await state.clear()
    plan_id, promo_id = _parse_confirm_callback(callback.data)
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

    try:
        pricing = await _resolve_display_pricing(session, settings, user.id, plan, promo_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    price = pricing.final_price

    if user.balance < price:
        text = EXTEND_INSUFFICIENT_BALANCE.format(balance=user.balance, price=price)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
        await callback.answer()
        return

    service = SubscriptionService(session, settings)
    try:
        sub = await service.extend_subscription(
            user.id, plan.id, payment_method=PaymentMethod.BALANCE, promo_code_id=promo_id
        )
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

    from src.services.notifications import notify_telegram_admins

    uname = f"@{user.username}" if user.username else (user.first_name or "—")
    await notify_telegram_admins(
        session,
        settings,
        (
            "💳 <b>Новый платёж — подписка (баланс)</b>\n\n"
            f"👤 {uname}\n"
            f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
            f"💎 Тариф: <b>{plan.name}</b>\n"
            f"💰 Сумма: <b>{price} ₽</b>\n"
            "🏦 Способ: баланс"
        ),
    )

@router.callback_query(F.data.startswith("sub:pay:yookassa:"))
async def process_purchase_yookassa(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    await state.clear()
    if not settings.yookassa_enabled:
        await callback.answer("Оплата через ЮKassa недоступна", show_alert=True)
        return

    parts = callback.data.split(":")
    plan_id = int(parts[3])
    promo_id = int(parts[4]) if len(parts) > 4 else None

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    plan = await PlanRepository(session).get_by_id(plan_id)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    payment_service = PaymentService(session, settings)
    try:
        order = await payment_service.create_purchase(user.id, plan_id, promo_code_id=promo_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    from src.bot.keyboards.inline import deposit_payment_keyboard

    text = PURCHASE_PAYMENT_CREATED.format(
        plan_name=plan.name,
        amount=order.amount,
        payment_url=order.payment_url,
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=deposit_payment_keyboard(order.id, order.payment_url),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "sub:reset")
async def ask_reset_subscription(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    service = SubscriptionService(session, settings)
    sub = await service.get_user_subscription(user.id)
    if not sub:
        await callback.answer("Нет активной подписки", show_alert=True)
        return

    from src.bot.keyboards.inline import reset_subscription_confirm

    await callback.message.edit_text(
        SUBSCRIPTION_RESET_CONFIRM,
        parse_mode="HTML",
        reply_markup=reset_subscription_confirm(),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:reset:confirm")
async def confirm_reset_subscription(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    service = SubscriptionService(session, settings)
    try:
        sub = await service.reset_subscription_link(user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
    text = SUBSCRIPTION_RESET_SUCCESS.format(subscription_url=sub_url)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer("✅ Ссылка обновлена!")
