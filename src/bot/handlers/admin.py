import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.helpers.menu import is_bot_admin
from src.bot.keyboards.inline import (
    admin_broadcast_confirm_keyboard,
    admin_list_keyboard,
    admin_panel_keyboard,
    to_main_menu_keyboard,
)
from src.bot.states import AdminBroadcastStates, AdminManageStates
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.notifications import broadcast_payload_to_all, send_broadcast_payload
from src.services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)

router = Router(name="admin")


async def _deny(message_or_callback, settings: Settings, session: AsyncSession) -> bool:
    user_id = message_or_callback.from_user.id
    if await is_bot_admin(user_id, settings, session):
        return False
    if isinstance(message_or_callback, CallbackQuery):
        message_or_callback.answer("Нет доступа", show_alert=True)
    else:
        message_or_callback.answer("⛔ Нет доступа.")
    return True


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if await _deny(callback, settings, session):
        return

    repo = UserRepository(session)
    users_count = len(await repo.list_all_telegram_ids())
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"Пользователей в базе: <b>{users_count}</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:admins")
async def admin_list(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if await _deny(callback, settings, session):
        return

    service = SystemSettingsService(session, settings)
    admin_ids = await service.get_all_bot_admin_ids()
    root_ids = set(settings.admin_telegram_ids)
    lines = ["👥 <b>Админы бота</b>\n"]
    for admin_id in admin_ids:
        marker = " 🔒 (.env)" if admin_id in root_ids else ""
        lines.append(f"• <code>{admin_id}</code>{marker}")
    lines.append("\n🔒 — главный админ, удалить нельзя")
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_list_keyboard(admin_ids, root_ids),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:admins:noop")
async def admin_list_noop(callback: CallbackQuery, settings: Settings, session: AsyncSession):
    if await _deny(callback, settings, session):
        return
    await callback.answer("Главного админа нельзя удалить", show_alert=True)


@router.callback_query(F.data == "admin:admins:add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession):
    if await _deny(callback, settings, session):
        return
    await state.set_state(AdminManageStates.waiting_add_id)
    await callback.message.answer("Введите Telegram ID нового админа:")
    await callback.answer()


@router.message(AdminManageStates.waiting_add_id)
async def admin_add_id(message: Message, state: FSMContext, session: AsyncSession, settings: Settings):
    if await _deny(message, settings, session):
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Telegram ID должен быть числом. Попробуйте ещё раз.")
        return

    admin_id = int(raw)
    service = SystemSettingsService(session, settings)
    admin_ids = await service.add_bot_admin_id(admin_id)
    await state.clear()
    await message.answer(
        f"✅ Админ <code>{admin_id}</code> добавлен.\nВсего админов: <b>{len(admin_ids)}</b>",
        parse_mode="HTML",
        reply_markup=admin_list_keyboard(admin_ids, set(settings.admin_telegram_ids)),
    )


@router.callback_query(F.data.startswith("admin:admins:remove:"))
async def admin_remove(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if await _deny(callback, settings, session):
        return

    admin_id = int(callback.data.rsplit(":", 1)[-1])
    service = SystemSettingsService(session, settings)
    try:
        admin_ids = await service.remove_bot_admin_id(admin_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    root_ids = set(settings.admin_telegram_ids)
    lines = ["👥 <b>Админы бота</b>\n"]
    for item_id in admin_ids:
        marker = " 🔒 (.env)" if item_id in root_ids else ""
        lines.append(f"• <code>{item_id}</code>{marker}")
    lines.append("\n🔒 — главный админ, удалить нельзя")
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_list_keyboard(admin_ids, root_ids),
    )
    await callback.answer(f"Админ {admin_id} удалён")


@router.callback_query(F.data == "admin:broadcast:all")
async def admin_broadcast_all_start(callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession):
    if await _deny(callback, settings, session):
        return

    await state.set_state(AdminBroadcastStates.waiting_content)
    await state.update_data(scope="all")
    await callback.message.answer(
        "📣 <b>Рассылка всем</b>\n\nОтправьте текст или фото с подписью.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast:one")
async def admin_broadcast_one_start(callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession):
    if await _deny(callback, settings, session):
        return

    await state.set_state(AdminBroadcastStates.waiting_target_id)
    await callback.message.answer("👤 Введите Telegram ID получателя:")
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_target_id)
async def admin_broadcast_one_target(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session: AsyncSession,
):
    if await _deny(message, settings, session):
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Telegram ID должен быть числом. Попробуйте ещё раз.")
        return

    await state.set_state(AdminBroadcastStates.waiting_content)
    await state.update_data(scope="one", target_id=int(raw))
    await message.answer(
        f"Отправьте текст или фото с подписью для пользователя <code>{raw}</code>.",
        parse_mode="HTML",
    )


@router.message(AdminBroadcastStates.waiting_content, F.photo)
async def admin_broadcast_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
):
    if await _deny(message, settings, session):
        await state.clear()
        return

    data = await state.get_data()
    scope = data.get("scope", "all")
    target_id = data.get("target_id")
    photo_file_id = message.photo[-1].file_id
    caption = (message.caption or "").strip()

    await state.update_data(
        kind="photo",
        photo_file_id=photo_file_id,
        caption=caption,
    )
    await state.set_state(AdminBroadcastStates.confirm)

    if scope == "one" and target_id:
        preview = f"Подтвердить отправку пользователю <code>{target_id}</code>?"
    else:
        repo = UserRepository(session)
        total = len(await repo.list_all_telegram_ids())
        preview = f"Подтвердить рассылку всем? Получателей: <b>{total}</b>"

    await message.answer(
        preview,
        parse_mode="HTML",
        reply_markup=admin_broadcast_confirm_keyboard(scope),
    )


@router.message(AdminBroadcastStates.waiting_content, F.text)
async def admin_broadcast_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
):
    if await _deny(message, settings, session):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Отправьте непустой текст или фото.")
        return

    data = await state.get_data()
    scope = data.get("scope", "all")
    target_id = data.get("target_id")

    await state.update_data(kind="text", text=text)
    await state.set_state(AdminBroadcastStates.confirm)

    if scope == "one" and target_id:
        preview = f"Подтвердить отправку пользователю <code>{target_id}</code>?"
    else:
        repo = UserRepository(session)
        total = len(await repo.list_all_telegram_ids())
        preview = f"Подтвердить рассылку всем? Получателей: <b>{total}</b>"

    await message.answer(
        preview,
        parse_mode="HTML",
        reply_markup=admin_broadcast_confirm_keyboard(scope),
    )


@router.callback_query(F.data.startswith("admin:broadcast:no:"), AdminBroadcastStates.confirm)
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession):
    if await _deny(callback, settings, session):
        return
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:broadcast:yes:"), AdminBroadcastStates.confirm)
async def admin_broadcast_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
):
    if await _deny(callback, settings, session):
        return

    data = await state.get_data()
    scope = data.get("scope", "all")
    kind = data.get("kind", "text")
    payload = {
        "kind": kind,
        "text": data.get("text") or "",
        "photo_file_id": data.get("photo_file_id"),
        "caption": data.get("caption") or "",
    }
    # Не отправляем «зависшие» подтверждения без контента (после рестарта FSM пустой).
    has_content = bool(payload.get("photo_file_id")) or bool((payload.get("text") or "").strip())
    if not has_content:
        await state.clear()
        await callback.message.edit_text("Нет сообщения для рассылки. Начните заново.")
        await callback.answer()
        return

    footer = to_main_menu_keyboard(settings)
    await state.clear()
    await callback.answer("Отправляю...")

    if scope == "one" and data.get("target_id"):
        ok = await send_broadcast_payload(
            settings,
            int(data["target_id"]),
            payload,
            reply_markup=footer,
        )
        await callback.message.edit_text("✅ Отправлено." if ok else "❌ Ошибка отправки.")
        return

    repo = UserRepository(session)
    telegram_ids = await repo.list_all_telegram_ids()
    ok_count, fail_count = await broadcast_payload_to_all(
        settings,
        payload,
        telegram_ids,
        reply_markup=footer,
    )
    await callback.message.edit_text(
        f"✅ Готово.\nУспешно: <b>{ok_count}</b>, ошибок: <b>{fail_count}</b>",
        parse_mode="HTML",
    )
