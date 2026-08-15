"""Личное сообщение пользователю по Telegram ID / username — только админам."""

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import direct_confirm_keyboard
from src.bot.keyboards.reply import (
    BTN_BROADCAST,
    BTN_DIRECT,
    BTN_MAIN_MENU,
    main_reply_keyboard,
)
from src.bot.states import DirectMessageStates
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.notifications import is_telegram_admin

logger = logging.getLogger(__name__)
router = Router(name="direct_message")

_TG_ID_RE = re.compile(r"^\d{5,15}$")
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


def _format_user_label(user) -> str:
    parts = []
    if user.username:
        parts.append(f"@{user.username}")
    name = " ".join(p for p in [user.first_name, user.last_name] if p)
    if name:
        parts.append(name)
    parts.append(f"ID <code>{user.telegram_id}</code>")
    return " · ".join(parts)


async def _resolve_target(session: AsyncSession, raw: str):
    """Возвращает (telegram_id, label, user|None) или (None, error, None)."""
    text = (raw or "").strip()
    if not text:
        return None, "Пустой ввод. Пришлите Telegram ID или @username.", None

    if text.startswith("@"):
        user = await UserRepository(session).get_by_username(text)
        if not user:
            return None, f"Пользователь <code>{text}</code> не найден в боте.", None
        return user.telegram_id, _format_user_label(user), user

    if _TG_ID_RE.match(text):
        telegram_id = int(text)
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user:
            return telegram_id, _format_user_label(user), user
        return (
            telegram_id,
            f"ID <code>{telegram_id}</code> (в базе бота не найден — отправим напрямую)",
            None,
        )

    # username без @
    if re.match(r"^[A-Za-z0-9_]{4,64}$", text):
        user = await UserRepository(session).get_by_username(text)
        if not user:
            return None, f"Пользователь <code>@{text}</code> не найден в боте.", None
        return user.telegram_id, _format_user_label(user), user

    return None, "Укажите числовой Telegram ID или username (@name).", None


@router.message(Command("message"))
@router.message(Command("dm"))
@router.message(F.text == BTN_DIRECT)
async def start_direct(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(message, session, settings):
        return

    await state.set_state(DirectMessageStates.waiting_target)
    await message.answer(
        "📨 <b>Личное сообщение</b>\n\n"
        "Пришлите получателя:\n"
        "• Telegram ID — <code>123456789</code>\n"
        "• или username — <code>@username</code>\n\n"
        "Отмена: /cancel",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), DirectMessageStates.waiting_target)
@router.message(Command("cancel"), DirectMessageStates.waiting_message)
@router.message(Command("cancel"), DirectMessageStates.confirm)
async def cancel_direct(message: Message, session: AsyncSession, settings: Settings, state: FSMContext):
    if not await _require_admin(message, session, settings):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "❌ Отправка отменена.",
        reply_markup=main_reply_keyboard(is_admin=True),
    )


@router.message(DirectMessageStates.waiting_target, ~F.text.in_(_REPLY_BUTTONS))
async def receive_target(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(message, session, settings):
        await state.clear()
        return

    telegram_id, label_or_error, _user = await _resolve_target(session, message.text or "")
    if telegram_id is None:
        await message.answer(f"⚠️ {label_or_error}\n\nПопробуйте ещё раз или /cancel", parse_mode="HTML")
        return

    await state.update_data(target_id=telegram_id, target_label=label_or_error)
    await state.set_state(DirectMessageStates.waiting_message)
    await message.answer(
        f"Получатель: <b>{label_or_error}</b>\n\n"
        "Теперь пришлите сообщение (текст, фото, видео, документ…).\n"
        "Отмена: /cancel",
        parse_mode="HTML",
    )


@router.message(DirectMessageStates.waiting_message, ~F.text.in_(_REPLY_BUTTONS))
async def receive_direct_message(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(message, session, settings):
        await state.clear()
        return

    if message.text and message.text.startswith("/"):
        await message.answer("Пришлите текст или медиа, либо /cancel")
        return

    data = await state.get_data()
    target_label = data.get("target_label", "—")
    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(DirectMessageStates.confirm)

    await message.answer(
        f"👁 <b>Предпросмотр выше.</b>\n\n"
        f"Отправить это сообщение?\n👤 {target_label}",
        parse_mode="HTML",
        reply_markup=direct_confirm_keyboard(),
    )


@router.callback_query(F.data == "dm:cancel", DirectMessageStates.confirm)
async def dm_cancel_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    if not await _require_admin(callback, session, settings):
        return
    await state.clear()
    await callback.message.edit_text("❌ Отправка отменена.")
    await callback.answer()


@router.callback_query(F.data == "dm:send", DirectMessageStates.confirm)
async def dm_send_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
    bot: Bot,
):
    if not await _require_admin(callback, session, settings):
        return

    data = await state.get_data()
    await state.clear()

    target_id = data.get("target_id")
    target_label = data.get("target_label", str(target_id))
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not target_id or not from_chat_id or not message_id:
        await callback.answer("Нет данных. Начните заново.", show_alert=True)
        return

    await callback.message.edit_text("⏳ Отправляю…")
    await callback.answer()

    try:
        await bot.copy_message(
            chat_id=target_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
        )
        await callback.message.answer(
            f"✅ Сообщение отправлено\n👤 {target_label}",
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(is_admin=True),
        )
    except TelegramForbiddenError:
        await callback.message.answer(
            f"🚫 Не удалось отправить: пользователь заблокировал бота.\n👤 {target_label}",
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(is_admin=True),
        )
    except TelegramRetryAfter as exc:
        await callback.message.answer(
            f"⏳ Лимит Telegram, подождите {exc.retry_after} сек. и попробуйте снова.",
            reply_markup=main_reply_keyboard(is_admin=True),
        )
    except Exception:
        logger.exception("Direct message failed for %s", target_id)
        await callback.message.answer(
            f"❌ Ошибка отправки.\n👤 {target_label}",
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(is_admin=True),
        )
