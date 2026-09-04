from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.helpers.menu import (
    is_bot_admin,
    is_main_menu_keyboard_text,
    send_main_menu,
    show_main_menu_callback,
)
from src.bot.texts.messages import BANNED, REFERRAL_WELCOME, WELCOME, WELCOME_BACK
from src.core.config import Settings
from src.repositories import UserRepository
from src.services.system_settings import SystemSettingsService

router = Router(name="start")


async def _send_start_menu(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    *,
    referral_code: str | None = None,
    partner_code: str | None = None,
) -> None:
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)

    if not user:
        referred_by_id = None
        partner_link_id = None
        if referral_code:
            referrer = await repo.resolve_referrer(
                referral_code if referral_code.startswith("ref_") else f"ref_{referral_code}"
            )
            if referrer and referrer.telegram_id != message.from_user.id:
                referred_by_id = referrer.id

        if partner_code:
            from src.services.partners import PartnerService

            partner = await PartnerService(session).get_by_code(partner_code, active_only=True)
            if partner:
                partner_link_id = partner.id

        user = await repo.create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            referred_by_id=referred_by_id,
            partner_link_id=partner_link_id,
        )
        text = WELCOME
        if referred_by_id:
            percent = await SystemSettingsService(session, settings).get_referral_bonus_percent()
            text += REFERRAL_WELCOME.format(bonus_percent=percent)
    else:
        # Keep profile fields fresh for personalised notifications.
        user.username = message.from_user.username
        user.first_name = message.from_user.first_name
        user.last_name = message.from_user.last_name
        name = user.first_name or user.username or "друг"
        text = WELCOME_BACK.format(name=name)

    if user.is_banned:
        await message.answer(
            BANNED.format(support_username=settings.support_username.lstrip("@")),
            parse_mode="HTML",
        )
        return

    await send_main_menu(
        message,
        settings,
        text,
        is_admin=await is_bot_admin(message.from_user.id, settings, session),
    )


@router.message(CommandStart(), StateFilter("*"))
async def cmd_start(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    await state.clear()

    referral_code = None
    partner_code = None
    if message.text and " " in message.text:
        args = message.text.split(maxsplit=1)[1]
        if args.startswith("ref_"):
            referral_code = args[4:]
        elif args.startswith("p_"):
            partner_code = args[2:]

    await _send_start_menu(
        message,
        session,
        settings,
        referral_code=referral_code,
        partner_code=partner_code,
    )


@router.message(F.text.func(is_main_menu_keyboard_text), StateFilter("*"))
async def keyboard_main_menu(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
):
    """Reply keyboard button from BotFather (text «Главное меню»)."""
    await state.clear()
    await _send_start_menu(message, session, settings)


@router.callback_query(lambda c: c.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, settings: Settings, session: AsyncSession):
    await show_main_menu_callback(
        callback,
        settings,
        is_admin=await is_bot_admin(callback.from_user.id, settings, session),
    )
    await callback.answer()
