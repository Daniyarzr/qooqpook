from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.enums import SubscriptionStatus, SuspensionReason
from src.core.utils import utcnow
from src.db.session import get_session
from src.repositories import SubscriptionRepository
from src.services.device_limit import DeviceLimitService
from src.services.devices import DeviceService
from src.services.traffic_sync import get_traffic_limit_gb
from src.services.vpn_config import (
    build_multi_vless_links_text,
    build_multi_vless_subscription_payload,
    build_subscription_payload,
    build_vless_link,
    build_xray_config,
    build_xray_config_json,
    sanitize_remark,
)

router = APIRouter()


def _subscription_userinfo(subscription) -> str:
    expire_ts = int(subscription.expires_at.timestamp())
    limit_gb = get_traffic_limit_gb(subscription)
    total = int(limit_gb * (1024**3)) if limit_gb else 0
    return (
        f"upload={subscription.bytes_upload};"
        f" download={subscription.bytes_download};"
        f" total={total};"
        f" expire={expire_ts}"
    )


def _check_active(subscription) -> None:
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.status == SubscriptionStatus.SUSPENDED:
        if subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value:
            raise HTTPException(status_code=403, detail="Subscription suspended: device limit exceeded")
        raise HTTPException(status_code=403, detail="Subscription inactive")
    if subscription.status == SubscriptionStatus.EXPIRED:
        raise HTTPException(status_code=403, detail="Subscription inactive")
    if subscription.expires_at <= utcnow():
        raise HTTPException(status_code=403, detail="Subscription expired")


async def _get_device_links(subscription, session, settings) -> list[tuple]:
    device_service = DeviceService(session, settings)
    devices = await device_service.list_devices(subscription.id)
    if not devices:
        devices = [await device_service.ensure_default_device(subscription)]

    user = subscription.user
    user_label = user.first_name or user.id if user else subscription.user_id
    return [
        (device.client_uuid, sanitize_remark(f"QooQ-VPN-{user_label}-{device.name}"))
        for device in devices
    ]


@router.get("/sub/{token}")
async def subscription_feed(
    request: Request,
    token: str,
    format: str = Query(default="base64", alias="format"),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """VPN client subscription endpoint (Hiddify / v2rayNG / Streisand)."""
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    user = subscription.user
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit_service = DeviceLimitService(session, settings)
    suspended = await limit_service.check_and_enforce(subscription, user, request)
    if suspended:
        raise HTTPException(status_code=403, detail="Subscription suspended: device limit exceeded")

    _check_active(subscription)

    device_links = await _get_device_links(subscription, session, settings)

    headers = {
        "subscription-userinfo": _subscription_userinfo(subscription),
        "profile-update-interval": "12",
        "profile-title": "QooQ VPN",
        "content-disposition": f'attachment; filename="qooq-{token[:8]}.txt"',
        "cache-control": "no-store",
    }

    if format == "json":
        client_uuid, remark = device_links[0]
        return JSONResponse(
            content=build_xray_config(client_uuid, remark),
            headers=headers,
        )

    if format in ("profile", "xjson", "full"):
        client_uuid, remark = device_links[0]
        payload = build_subscription_payload(client_uuid, remark)
        return PlainTextResponse(content=payload, media_type="text/plain; charset=utf-8", headers=headers)

    if format == "link":
        return PlainTextResponse(
            content=build_multi_vless_links_text(device_links),
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    payload = build_multi_vless_subscription_payload(device_links)
    return PlainTextResponse(content=payload, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/sub/{token}/raw")
async def subscription_raw_json(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Raw JSON config for debugging."""
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    user = subscription.user
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit_service = DeviceLimitService(session, settings)
    suspended = await limit_service.check_and_enforce(subscription, user, request)
    if suspended:
        raise HTTPException(status_code=403, detail="Subscription suspended: device limit exceeded")

    _check_active(subscription)

    device_links = await _get_device_links(subscription, session, settings)
    client_uuid, remark = device_links[0]
    return Response(
        content=build_xray_config_json(client_uuid, remark),
        media_type="application/json",
        headers={
            "subscription-userinfo": _subscription_userinfo(subscription),
        },
    )
