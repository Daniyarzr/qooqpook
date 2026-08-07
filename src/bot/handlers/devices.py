from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import back_to_menu, devices_keyboard
from src.bot.texts.messages import (
    DEVICES_HEADER,
    DEVICES_ITEM,
    SUBSCRIPTION_RESTORED,
)
from src.core.config import Settings
from src.core.enums import SubscriptionStatus, SuspensionReason
from src.core.utils import bytes_to_gb, format_datetime_ru
from src.repositories import UserRepository
from src.services import SubscriptionService
from src.services.device_limit import DeviceLimitService
from src.services.devices import DeviceService

router = Router(name="devices")


async def _get_subscription(repo, user_id, session):
    sub_service = SubscriptionService(session, None)
    return await sub_service.subscriptions.get_current_by_user(user_id)


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

    device_service = DeviceService(session, settings)
    devices = await device_service.list_devices(subscription.id)
    if not devices:
        devices = [await device_service.ensure_default_device(subscription)]

    limit_service = DeviceLimitService(session, settings)
    hwid_count = await limit_service.count_hwids(subscription.id)
    suspended = (
        subscription.status == SubscriptionStatus.SUSPENDED
        and subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value
    )
    can_restore = (
        suspended
        and len(devices) <= settings.max_devices_per_subscription
    )

    text = DEVICES_HEADER.format(
        count=max(len(devices), hwid_count),
        max_devices=settings.max_devices_per_subscription,
    )
    if suspended:
        text += f"\n⚠️ Подключений зафиксировано: <b>{hwid_count}</b>\n"
    for device in devices:
        total_gb = bytes_to_gb(device.bytes_upload + device.bytes_download)
        text += DEVICES_ITEM.format(
            name=device.name,
            uuid=str(device.client_uuid),
            traffic=f"{total_gb:.2f}",
            created=format_datetime_ru(device.created_at),
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=devices_keyboard(
            devices,
            len(devices) < settings.max_devices_per_subscription and not suspended,
            can_restore=can_restore,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:device:add")
async def add_device(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription or subscription.status == SubscriptionStatus.SUSPENDED:
        await callback.answer("Подписка недоступна", show_alert=True)
        return

    device_service = DeviceService(session, settings)
    try:
        await device_service.add_device(subscription)
        await sub_service.sync_xray_clients()
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer("✅ Устройство добавлено")
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
    if await limit_service.try_reactivate(subscription):
        await callback.answer("🗑 Удалено · подписка восстановлена")
    else:
        await callback.answer("🗑 Устройство удалено")
    await show_devices(callback, session, settings)


@router.callback_query(F.data == "sub:restore")
async def restore_subscription(callback: CallbackQuery, session: AsyncSession, settings: Settings):
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
    device_service = DeviceService(session, settings)
    devices = await device_service.list_devices(subscription.id)
    if len(devices) > settings.max_devices_per_subscription:
        await callback.answer(
            f"Удалите лишние устройства ({len(devices)}/{settings.max_devices_per_subscription})",
            show_alert=True,
        )
        return

    if not await limit_service.try_reactivate(subscription):
        await callback.answer("Не удалось восстановить. Удалите лишние устройства.", show_alert=True)
        return

    await callback.message.edit_text(
        SUBSCRIPTION_RESTORED,
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await callback.answer("✅ Подписка восстановлена")
