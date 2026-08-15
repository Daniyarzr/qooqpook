from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu
from src.bot.keyboards.reply import main_reply_keyboard
from src.bot.texts.messages import WELCOME
from src.core.config import Settings
from src.services.system_settings import SystemSettingsService

MAIN_MENU_KEYBOARD_LABELS = frozenset(
    {
        "Главное меню",
        "🏠 Главное меню",
        "📋 Главное меню",
        "Main menu",
    }
)


def is_main_menu_keyboard_text(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.strip()
    if normalized in MAIN_MENU_KEYBOARD_LABELS:
        return True
    return normalized.casefold() == "главное меню"


def is_root_bot_admin(telegram_id: int, settings: Settings) -> bool:
    return telegram_id in settings.admin_telegram_ids


async def is_bot_admin(telegram_id: int, settings: Settings, session: AsyncSession) -> bool:
    admin_ids = await SystemSettingsService(session, settings).get_all_bot_admin_ids()
    return telegram_id in admin_ids


async def send_main_menu(
    message: Message,
    settings: Settings,
    text: str = WELCOME,
    *,
    is_admin: bool = False,
) -> None:
    # Reply-клавиатура внизу экрана + inline-кнопки в сообщении.
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )
    await message.answer(
        "Выберите действие 👇",
        parse_mode="HTML",
        reply_markup=main_menu(settings, is_admin=is_admin),
    )


async def show_main_menu_callback(
    callback: CallbackQuery,
    settings: Settings,
    text: str = WELCOME,
    *,
    is_admin: bool = False,
) -> None:
    from aiogram.exceptions import TelegramBadRequest

    markup = main_menu(settings, is_admin=is_admin)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)
