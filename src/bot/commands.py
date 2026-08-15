"""Команды синей кнопки «Меню» слева от поля ввода."""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands


async def setup_bot_commands(bot: Bot) -> None:
    """Только /start — как на эталонном боте."""
    await bot.set_my_commands(
        [BotCommand(command="start", description="Запустить бота")],
        scope=BotCommandScopeDefault(),
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
