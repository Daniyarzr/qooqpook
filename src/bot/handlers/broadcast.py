"""Рассылка сообщений из бота — только для Telegram-админов из админки."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import broadcast_confirm_keyboard, broadcast_menu_keyboard
from src.bot.keyboards.reply import (
    BTN_BROADCAST,
    BTN_DIRECT,
    BTN_MAIN_MENU,
    main_reply_keyboard,
)
from src.bot.states import BroadcastStates
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.notifications import is_telegram_admin

logger = logging.getLogger(__name__)
router = Router(name="broadcast")

# ~20 сообщений/сек — безопасный темп для Telegram
_SEND_DELAY_SEC = 0.05
_REPLY_BUTTONS = {BTN_MAIN_MENU, BTN_BROADCAST, BTN_DIRECT}


async def _require_admin(
    message_or_callback: Message | CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> bool:
    user = message_or_callback.from_user
    if not user:
        return False
    if await is_telegram_admin(session, user.id, settings):
        return True
    text = "⛔ Команда доступна только администраторам."
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer(text, show_alert=True)
    else:
        await message_or_callback.answer(text)
    return False


@router.message(Command("broadcast"))
@router.message(F.text == BTN_BROADCAST)
async def start_broadcast(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(message, session, settings):
        return

    await state.set_state(BroadcastStates.waiting_message)
    await message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Пришлите сообщение, которое нужно отправить всем пользователям бота.\n"
        "Можно текст, фото, видео, документ или другой контент.\n\n"
        "Отмена: /cancel",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), BroadcastStates.waiting_message)
@router.message(Command("cancel"), BroadcastStates.confirm)
async def cancel_broadcast(message: Message, session: AsyncSession, settings: Settings, state: FSMContext):
    if not await _require_admin(message, session, settings):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "❌ Рассылка отменена.",
        reply_markup=main_reply_keyboard(is_admin=True),
    )


@router.message(BroadcastStates.waiting_message, ~F.text.in_(_REPLY_BUTTONS))
async def receive_broadcast_message(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(message, session, settings):
        await state.clear()
        return

    if message.text and message.text.startswith("/"):
        await message.answer("Пришлите текст или медиа для рассылки, либо /cancel")
        return

    users = await UserRepository(session).list_broadcast_telegram_ids()
    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        recipients=len(users),
    )
    await state.set_state(BroadcastStates.confirm)

    await message.answer(
        f"👁 <b>Предпросмотр выше.</b>\n\n"
        f"Получателей: <b>{len(users)}</b> (без заблокированных).\n"
        f"Отправить это сообщение всем?",
        parse_mode="HTML",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "broadcast:cancel", BroadcastStates.confirm)
async def broadcast_cancel_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(callback, session, settings):
        return
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "broadcast:send", BroadcastStates.confirm)
async def broadcast_send_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
    bot: Bot,
):
    if not await _require_admin(callback, session, settings):
        return

    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")
    await state.clear()

    if not from_chat_id or not message_id:
        await callback.answer("Нет сообщения для рассылки. Начните заново.", show_alert=True)
        return

    recipients = await UserRepository(session).list_broadcast_telegram_ids()
    await callback.message.edit_text(
        f"⏳ Рассылка запущена…\nПолучателей: <b>{len(recipients)}</b>",
        parse_mode="HTML",
    )
    await callback.answer()

    # Дальше сессия БД не нужна — отправляем через Bot API
    menu_kb = broadcast_menu_keyboard()
    sent = 0
    failed = 0
    blocked = 0

    for telegram_id in recipients:
        try:
            await bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                reply_markup=menu_kb,
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            failed += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
            try:
                await bot.copy_message(
                    chat_id=telegram_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                    reply_markup=menu_kb,
                )
                sent += 1
            except Exception:
                failed += 1
                logger.exception("Broadcast retry failed for %s", telegram_id)
        except Exception:
            failed += 1
            logger.exception("Broadcast failed for %s", telegram_id)

        await asyncio.sleep(_SEND_DELAY_SEC)

    await callback.message.answer(
        "✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"❌ Ошибки: <b>{failed - blocked}</b>\n"
        f"👥 Всего в базе: <b>{len(recipients)}</b>",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(is_admin=True),
    )
