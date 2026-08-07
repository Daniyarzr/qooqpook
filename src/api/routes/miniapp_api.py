from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps.miniapp_auth import get_or_create_miniapp_user
from src.core.config import Settings, get_settings
from src.core.enums import PaymentStatus, SubscriptionStatus, SuspensionReason
from src.core.utils import (
    build_referral_link,
    build_subscription_url,
    bytes_to_gb,
    format_datetime_ru,
    format_duration_until,
)
from src.db.session import get_session
from src.models import User
from src.repositories import PlanRepository, UserRepository
from src.schemas import (
    MiniAppBootstrapResponse,
    MiniAppDepositRequest,
    MiniAppDepositResponse,
    MiniAppDepositStatusResponse,
    MiniAppDeviceRead,
    MiniAppPromoValidateRequest,
    MiniAppPromoValidateResponse,
    MiniAppPurchaseRequest,
    MiniAppReferralRead,
    MiniAppSettingsRead,
    MiniAppSubscriptionRead,
    SubscriptionPlanRead,
    TransactionRead,
    UserRead,
)
from src.services import BalanceService, SubscriptionService
from src.services.device_limit import DeviceLimitService
from src.services.devices import DeviceService
from src.services.payment import PaymentService
from src.services.pricing import PurchasePricingService
from src.services.promo import PromoCodeService
from src.services.referral import ReferralService
from src.services.system_settings import SystemSettingsService

router = APIRouter(prefix="/api/v1/miniapp")


async def _build_subscription_read(
    session: AsyncSession,
    settings: Settings,
    user_id: int,
) -> tuple[MiniAppSubscriptionRead | None, list[MiniAppDeviceRead]]:
    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user_id)
    if not subscription:
        return None, []

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
    can_restore = suspended and len(devices) <= settings.max_devices_per_subscription

    sub_read = MiniAppSubscriptionRead(
        id=subscription.id,
        status=subscription.status,
        expires_at=subscription.expires_at,
        expires_at_formatted=format_datetime_ru(subscription.expires_at),
        is_trial=subscription.is_trial,
        subscription_url=build_subscription_url(settings.hub_domain, subscription.subscription_token),
        duration_remaining=format_duration_until(subscription.expires_at),
        device_count=max(len(devices), hwid_count),
        max_devices=settings.max_devices_per_subscription,
        suspended_device_limit=suspended,
        can_restore=can_restore,
        hwid_count=hwid_count,
    )

    device_reads = [
        MiniAppDeviceRead(
            id=device.id,
            name=device.name,
            client_uuid=device.client_uuid,
            traffic_gb=bytes_to_gb(device.bytes_upload + device.bytes_download),
            created_at=device.created_at,
        )
        for device in devices
    ]
    return sub_read, device_reads


async def build_bootstrap(
    session: AsyncSession,
    settings: Settings,
    user: User,
    referral_welcome: bool = False,
) -> MiniAppBootstrapResponse:
    subscription, devices = await _build_subscription_read(session, settings, user.id)

    plans = await PlanRepository(session).get_active_plans()
    transactions = await BalanceService(session).get_history(user.id, limit=15)

    referrals_count = await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by_id == user.id)
    ) or 0

    settings_service = SystemSettingsService(session, settings)
    referral_service = ReferralService(session, settings)
    bonus_percent = await settings_service.get_referral_bonus_percent()
    total_earned = await referral_service.total_bonus_earned(user.id)

    return MiniAppBootstrapResponse(
        user=UserRead.model_validate(user),
        subscription=subscription,
        devices=devices,
        plans=[SubscriptionPlanRead.model_validate(plan) for plan in plans],
        transactions=[TransactionRead.model_validate(tx) for tx in transactions],
        referral=MiniAppReferralRead(
            referral_link=build_referral_link(settings.bot_username, user.referral_code),
            referral_code=user.referral_code,
            bonus_percent=bonus_percent,
            referrals_count=referrals_count,
            total_earned=total_earned,
        ),
        settings=MiniAppSettingsRead(
            trial_days=settings.trial_days,
            max_devices=settings.max_devices_per_subscription,
            deposit_amounts=settings.deposit_amounts,
            yookassa_enabled=settings.yookassa_enabled,
            bot_username=settings.bot_username,
            referral_welcome=referral_welcome,
        ),
    )


@router.get("/bootstrap", response_model=MiniAppBootstrapResponse)
async def bootstrap(
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, referral_welcome = auth
    return await build_bootstrap(session, settings, user, referral_welcome=referral_welcome)


@router.post("/trial", response_model=MiniAppBootstrapResponse)
async def activate_trial(
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    if user.trial_used:
        raise HTTPException(status_code=400, detail="Trial already used")

    service = SubscriptionService(session, settings)
    try:
        await service.activate_trial(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = await UserRepository(session).get_by_id(user.id)
    return await build_bootstrap(session, settings, user)


@router.post("/purchase", response_model=MiniAppBootstrapResponse)
async def purchase_plan(
    body: MiniAppPurchaseRequest,
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    plan = await PlanRepository(session).get_by_id(body.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        pricing = await PurchasePricingService(session, settings).resolve(
            user.id, plan, body.promo_code_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if user.balance < pricing.final_price:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance: need {pricing.final_price} ₽, have {user.balance} ₽",
        )

    service = SubscriptionService(session, settings)
    try:
        await service.extend_subscription(user.id, plan.id, promo_code_id=body.promo_code_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = await UserRepository(session).get_by_id(user.id)
    return await build_bootstrap(session, settings, user)


@router.post("/promo/validate", response_model=MiniAppPromoValidateResponse)
async def validate_promo(
    body: MiniAppPromoValidateRequest,
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    plan = await PlanRepository(session).get_by_id(body.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    code = body.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Enter promo code")

    promo_service = PromoCodeService(session)
    try:
        promo_validation = await promo_service.validate(code, user.id, plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pricing = await PurchasePricingService(session, settings).resolve(
        user.id, plan, promo_validation.promo.id
    )

    return MiniAppPromoValidateResponse(
        promo_code_id=promo_validation.promo.id,
        code=promo_validation.promo.code,
        discount_amount=pricing.discount_amount,
        final_price=pricing.final_price,
        original_price=pricing.original_price,
    )


@router.post("/deposit", response_model=MiniAppDepositResponse)
async def create_deposit(
    body: MiniAppDepositRequest,
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="Deposits are temporarily unavailable")

    service = PaymentService(session, settings)
    try:
        order = await service.create_deposit(user.id, body.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MiniAppDepositResponse(
        order_id=order.id,
        payment_url=order.payment_url or "",
        amount=order.amount,
        status=order.status,
    )


@router.get("/deposit/{order_id}", response_model=MiniAppDepositStatusResponse)
async def check_deposit(
    order_id: int,
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    service = PaymentService(session, settings)
    order = await service.check_order(order_id, user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Payment not found")

    balance = None
    if order.status == PaymentStatus.SUCCEEDED:
        refreshed_user = await UserRepository(session).get_by_id(user.id)
        balance = refreshed_user.balance if refreshed_user else None

    return MiniAppDepositStatusResponse(
        order_id=order.id,
        status=order.status,
        balance=balance,
    )


@router.post("/devices", response_model=MiniAppBootstrapResponse)
async def add_device(
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription or subscription.status == SubscriptionStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="Subscription unavailable")

    device_service = DeviceService(session, settings)
    try:
        await device_service.add_device(subscription)
        await sub_service.sync_xray_clients()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await build_bootstrap(session, settings, user)


@router.delete("/devices/{device_id}", response_model=MiniAppBootstrapResponse)
async def delete_device(
    device_id: int,
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        raise HTTPException(status_code=400, detail="No subscription")

    device_service = DeviceService(session, settings)
    if not await device_service.delete_device(device_id, subscription.id):
        raise HTTPException(status_code=404, detail="Device not found")

    await sub_service.sync_xray_clients()
    limit_service = DeviceLimitService(session, settings)
    await limit_service.try_reactivate(subscription)

    return await build_bootstrap(session, settings, user)


@router.post("/devices/restore", response_model=MiniAppBootstrapResponse)
async def restore_subscription(
    auth: tuple[User, bool] = Depends(get_or_create_miniapp_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user, _ = auth
    sub_service = SubscriptionService(session, settings)
    subscription = await sub_service.subscriptions.get_current_by_user(user.id)
    if not subscription:
        raise HTTPException(status_code=400, detail="No subscription")

    device_service = DeviceService(session, settings)
    devices = await device_service.list_devices(subscription.id)
    if len(devices) > settings.max_devices_per_subscription:
        raise HTTPException(
            status_code=400,
            detail=f"Remove extra devices ({len(devices)}/{settings.max_devices_per_subscription})",
        )

    limit_service = DeviceLimitService(session, settings)
    if not await limit_service.try_reactivate(subscription):
        raise HTTPException(status_code=400, detail="Could not restore subscription")

    return await build_bootstrap(session, settings, user)
