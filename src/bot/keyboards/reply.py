from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard — кнопка «Главное меню» от BotFather/бота."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Главное меню")]],
        resize_keyboard=True,
        is_persistent=True,
    )
