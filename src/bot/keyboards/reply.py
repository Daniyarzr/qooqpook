"""Постоянная reply-клавиатура."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_MAIN_MENU = "🏠 Главное меню"
BTN_BROADCAST = "📢 Рассылка"
BTN_DIRECT = "📨 Сообщение"


def main_reply_keyboard(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=BTN_MAIN_MENU)],
    ]
    if is_admin:
        rows.append(
            [
                KeyboardButton(text=BTN_BROADCAST),
                KeyboardButton(text=BTN_DIRECT),
            ]
        )
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Нажмите «Главное меню» или выберите команду…",
    )
