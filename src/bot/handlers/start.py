from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu
from src.bot.texts.messages import BANNED, REFERRAL_WELCOME, WELCOME, WELCOME_BACK
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.system_settings import SystemSettingsService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)

    referral_code = None
    if message.text and " " in message.text:
        args = message.text.split(maxsplit=1)[1]
        if args.startswith("ref_"):
            referral_code = args[4:]

    if not user:
        referred_by_id = None
        if referral_code:
            referrer = await repo.get_by_referral_code(referral_code)
            if referrer:
                referred_by_id = referrer.id

        user = await repo.create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            referred_by_id=referred_by_id,
        )
        text = WELCOME
        if referred_by_id:
            percent = await SystemSettingsService(session, settings).get_referral_discount_percent()
            text += REFERRAL_WELCOME.format(discount_percent=percent)
    else:
        name = user.first_name or user.username or "друг"
        text = WELCOME_BACK.format(name=name)

    if user.is_banned:
        await message.answer(BANNED, parse_mode="HTML")
        return

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(settings),
    )


@router.callback_query(lambda c: c.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, settings: Settings):
    await callback.message.edit_text(
        WELCOME,
        parse_mode="HTML",
        reply_markup=main_menu(settings),
    )
    await callback.answer()


@router.message(Command("menu"))
async def cmd_menu(message: Message, settings: Settings):
    await message.answer(
        WELCOME,
        parse_mode="HTML",
        reply_markup=main_menu(settings),
    )
