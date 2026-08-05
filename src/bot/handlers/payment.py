from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import balance_menu, deposit_amounts_keyboard, deposit_payment_keyboard
from src.bot.texts.messages import (
    DEPOSIT_CREATED,
    DEPOSIT_NOT_CONFIGURED,
    DEPOSIT_PENDING,
    DEPOSIT_SUCCESS,
)
from src.core.config import Settings
from src.core.enums import PaymentStatus
from src.repositories import UserRepository
from src.services.payment import PaymentService

router = Router(name="payment")


@router.callback_query(F.data == "balance:topup")
async def start_topup(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not settings.yookassa_enabled:
        await callback.answer(DEPOSIT_NOT_CONFIGURED, show_alert=True)
        return

    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    await callback.message.edit_text(
        "💳 <b>Пополнение баланса</b>\n\nВыберите сумму:",
        parse_mode="HTML",
        reply_markup=deposit_amounts_keyboard(settings.deposit_amounts),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("balance:topup:"))
async def create_deposit(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not settings.yookassa_enabled:
        await callback.answer(DEPOSIT_NOT_CONFIGURED, show_alert=True)
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
    service = PaymentService(session, settings)
    order = await service.check_order(order_id, user.id)

    if not order:
        await callback.answer("Платёж не найден", show_alert=True)
        return

    if order.status == PaymentStatus.SUCCEEDED:
        user = await repo.get_by_id(user.id)
        text = DEPOSIT_SUCCESS.format(amount=order.amount, balance=user.balance)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=balance_menu(settings.yookassa_enabled),
        )
        await callback.answer("Оплата получена!")
        return

    await callback.answer(DEPOSIT_PENDING, show_alert=True)
