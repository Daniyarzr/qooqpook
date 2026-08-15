from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import (
    back_to_menu,
    balance_menu,
    deposit_amounts_keyboard,
    deposit_payment_keyboard,
)
from src.bot.states import DepositStates
from src.bot.texts.messages import (
    DEPOSIT_ASK_AMOUNT,
    DEPOSIT_CREATED,
    DEPOSIT_NOT_CONFIGURED,
    DEPOSIT_PENDING,
    DEPOSIT_SUCCESS,
    PURCHASE_PAYMENT_SUCCESS,
)
from src.core.config import Settings
from src.core.enums import PaymentOrderPurpose, PaymentStatus
from src.core.utils import build_subscription_url, format_datetime_ru, format_duration_until
from src.repositories import UserRepository
from src.services import SubscriptionService
from src.services.payment import PaymentService

router = Router(name="payment")


def _deposit_unavailable(settings: Settings) -> str:
    return DEPOSIT_NOT_CONFIGURED.format(
        support_username=settings.support_username.lstrip("@")
    )


@router.callback_query(F.data == "balance:topup")
async def start_topup(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not settings.yookassa_enabled:
        await callback.answer(_deposit_unavailable(settings), show_alert=True)
        return

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    await callback.message.edit_text(
        "💳 <b>Пополнение баланса</b>\n\nВыберите сумму или введите свою:",
        parse_mode="HTML",
        reply_markup=deposit_amounts_keyboard(settings.deposit_amounts),
    )
    await callback.answer()


@router.callback_query(F.data == "balance:topup:custom")
async def ask_custom_amount(
    callback: CallbackQuery, state: FSMContext, settings: Settings
):
    if not settings.yookassa_enabled:
        await callback.answer(_deposit_unavailable(settings), show_alert=True)
        return

    await state.set_state(DepositStates.waiting_amount)
    await callback.message.edit_text(
        DEPOSIT_ASK_AMOUNT.format(
            min_amount=settings.deposit_min_amount,
            max_amount=settings.deposit_max_amount,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DepositStates.waiting_amount)
async def process_custom_amount(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("Введите число, например: 500")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше 0")
        return

    await state.clear()
    service = PaymentService(session, settings)
    try:
        order = await service.create_deposit(user.id, amount)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    text = DEPOSIT_CREATED.format(amount=amount, payment_url=order.payment_url)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=deposit_payment_keyboard(order.id, order.payment_url),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("balance:topup:"))
async def create_deposit(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if callback.data == "balance:topup:custom":
        return

    if not settings.yookassa_enabled:
        await callback.answer(_deposit_unavailable(settings), show_alert=True)
        return

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    amount_str = callback.data.split(":")[-1]
    try:
        amount = Decimal(amount_str)
    except Exception:
        await callback.answer("Неверная сумма", show_alert=True)
        return

    service = PaymentService(session, settings)
    try:
        order = await service.create_deposit(user.id, amount)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    text = DEPOSIT_CREATED.format(amount=amount, payment_url=order.payment_url)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=deposit_payment_keyboard(order.id, order.payment_url),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("balance:check:"))
async def check_deposit(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    order_id = int(callback.data.split(":")[-1])
    await callback.answer("⏳ Проверяем оплату...")

    service = PaymentService(session, settings)
    order = await service.check_order(order_id, user.id)

    if not order:
        await callback.message.answer("Платёж не найден")
        return

    if order.status == PaymentStatus.SUCCEEDED:
        if order.purpose == PaymentOrderPurpose.SUBSCRIPTION:
            sub_service = SubscriptionService(session, settings)
            sub = await sub_service.get_user_subscription(user.id)
            if sub:
                sub_url = build_subscription_url(settings.hub_domain, sub.subscription_token)
                text = PURCHASE_PAYMENT_SUCCESS.format(
                    expires_at=format_datetime_ru(sub.expires_at),
                    duration=format_duration_until(sub.expires_at),
                    subscription_url=sub_url,
                )
            else:
                text = "✅ Оплата получена! Подписка активирована."
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu())
            return

        user = await repo.get_by_id(user.id)
        text = DEPOSIT_SUCCESS.format(amount=order.amount, balance=user.balance)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=balance_menu(settings.yookassa_enabled),
        )
        return

    await callback.message.answer(DEPOSIT_PENDING)
