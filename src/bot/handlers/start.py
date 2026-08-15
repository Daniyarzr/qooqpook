from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu
from src.bot.keyboards.reply import main_reply_keyboard
from src.bot.texts.messages import BANNED, REFERRAL_WELCOME, WELCOME, WELCOME_BACK
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.notifications import is_telegram_admin
from src.services.system_settings import SystemSettingsService

router = Router(name="start")


async def _send_home(
    message: Message,
    text: str,
    settings: Settings,
    *,
    is_admin: bool = False,
) -> None:
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(is_admin=is_admin),
    )
    await message.answer(
        "Выберите действие 👇",
        reply_markup=main_menu(settings),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    await state.clear()
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
            percent = await SystemSettingsService(session, settings).get_referral_bonus_percent()
            text += REFERRAL_WELCOME.format(bonus_percent=percent)
    else:
        name = user.first_name or user.username or "друг"
        text = WELCOME_BACK.format(name=name)

    if user.is_banned:
        await message.answer(BANNED, parse_mode="HTML")
        return

    admin = await is_telegram_admin(session, message.from_user.id, settings)
    await _send_home(message, text, settings, is_admin=admin)


@router.callback_query(lambda c: c.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    from src.services.notifications import is_telegram_admin

    admin = await is_telegram_admin(session, callback.from_user.id, settings)
    text = WELCOME
    markup = main_menu(settings)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(is_admin=admin),
        )
        await callback.message.answer("Выберите действие 👇", reply_markup=markup)
    await callback.answer()
