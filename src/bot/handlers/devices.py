from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, devices_keyboard
from src.bot.texts.messages import (
    DEVICES_HEADER,
    DEVICES_ITEM,
    DEVICES_NONE,
    SUBSCRIPTION_RESTORED,
)
from src.core.config import Settings
from src.core.enums import SubscriptionStatus, SuspensionReason
from src.core.utils import format_datetime_ru
from src.repositories import UserRepository
from src.services import SubscriptionService
from src.services.device_limit import DeviceLimitService, hwid_display_name
from src.services.devices import DeviceService

router = Router(name="devices")


class _HwidButton:
    __slots__ = ("id", "label")

    def __init__(self, entry_id: int, label: str):
        self.id = entry_id
        self.label = label


@router.callback_query(F.data == "sub:devices")
async def show_devices(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        await callback.answer("Нет подписки", show_alert=True)
        return

    limit_service = DeviceLimitService(session, settings)
    await limit_service.purge_phantom_hwids(subscription.id)
    if (
        subscription.status == SubscriptionStatus.SUSPENDED
        and subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value
    ):
        await limit_service.lift_legacy_device_limit_suspend(subscription)

    hwids = await limit_service.list_hwids(subscription.id)
    max_devices = settings.max_devices_per_subscription
    hwid_count = len(hwids)
    overflow = hwid_count > max_devices

    text = DEVICES_HEADER.format(count=hwid_count, max_devices=max_devices)
    if overflow:
        text += (
            f"\n⛔ Лишних: <b>{hwid_count - max_devices}</b> "
            f"(им доступ закрыт, пока не удалите).\n"
        )

    hwid_buttons: list[_HwidButton] = []
    if not hwids:
        text += DEVICES_NONE
    else:
        for idx, entry in enumerate(hwids):
            name = hwid_display_name(entry.hwid, entry.user_agent)
            status = "✅" if idx < max_devices else "⛔"
            text += DEVICES_ITEM.format(
                status=status,
                name=name,
                uuid=entry.hwid,
                created=format_datetime_ru(entry.last_seen_at or entry.first_seen_at),
            )
            prefix = "✅ " if idx < max_devices else "⛔ "
            hwid_buttons.append(_HwidButton(entry.id, prefix + name))

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=devices_keyboard(
            hwids=hwid_buttons,
            can_add=False,
            can_restore=False,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:hwid:del:"))
async def delete_hwid(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    hwid_id = int(callback.data.split(":")[-1])
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        await callback.answer("Нет подписки", show_alert=True)
        return

    limit_service = DeviceLimitService(session, settings)
    if not await limit_service.delete_hwid(subscription.id, hwid_id):
        await callback.answer("Устройство не найдено", show_alert=True)
        return

    if (
        subscription.status == SubscriptionStatus.SUSPENDED
        and subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value
    ):
        await limit_service.lift_legacy_device_limit_suspend(subscription)
        await callback.answer("🗑 Удалено · доступ восстановлен")
    else:
        await callback.answer("🗑 Устройство удалено")
    await show_devices(callback, session, settings)


@router.callback_query(F.data.startswith("sub:device:del:"))
async def delete_device(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    device_id = int(callback.data.split(":")[-1])
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        await callback.answer("Нет подписки", show_alert=True)
        return

    device_service = DeviceService(session, settings)
    if not await device_service.delete_device(device_id, subscription.id):
        await callback.answer("Устройство не найдено", show_alert=True)
        return

    await sub_service.sync_xray_clients()

    limit_service = DeviceLimitService(session, settings)
    if (
        subscription.status == SubscriptionStatus.SUSPENDED
        and subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value
    ):
        await limit_service.lift_legacy_device_limit_suspend(subscription)
        await callback.answer("🗑 Удалено · доступ восстановлен")
    else:
        await callback.answer("🗑 Устройство удалено")
    await show_devices(callback, session, settings)


@router.callback_query(F.data == "sub:restore")
async def restore_subscription(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    """Legacy: снимает старую глобальную заморозку по лимиту устройств."""
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        await callback.answer("Нет подписки", show_alert=True)
        return

    limit_service = DeviceLimitService(session, settings)
    await limit_service.purge_phantom_hwids(subscription.id)
    if not await limit_service.try_reactivate(subscription, clear_hwids=False):
        await callback.answer(
            "Подписка уже активна. Лишние устройства просто не получают доступ.",
            show_alert=True,
        )
        return

    from src.core.utils import build_subscription_url

    sub_url = build_subscription_url(settings.hub_domain, subscription.subscription_token)
    text = (
        f"{SUBSCRIPTION_RESTORED.strip()}\n\n"
        f"🔗 Ссылка подписки:\n<code>{sub_url}</code>\n\n"
        "Обновите подписку в VPN-клиенте (потяните вниз / Update)."
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await callback.answer("✅ Подписка восстановлена")
