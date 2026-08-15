"""Обработчик кнопки reply-клавиатуры «Главное меню»."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu
from src.bot.keyboards.reply import BTN_MAIN_MENU, main_reply_keyboard
from src.bot.texts.messages import WELCOME
from src.core.config import Settings
from src.services.notifications import is_telegram_admin

router = Router(name="reply_menu")


@router.message(F.text == BTN_MAIN_MENU)
async def on_main_menu(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    # Сбрасываем FSM (рассылка / ЛС), иначе кнопка уходит в «ожидание сообщения»
    await state.clear()
    admin = await is_telegram_admin(session, message.from_user.id, settings)
    await message.answer(
        WELCOME,
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(is_admin=admin),
    )
    await message.answer(
        "Выберите действие 👇",
        reply_markup=main_menu(settings),
    )
