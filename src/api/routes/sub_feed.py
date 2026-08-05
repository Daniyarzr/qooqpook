from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.enums import SubscriptionStatus
from src.core.utils import utcnow
from src.db.session import get_session
from src.repositories import SubscriptionRepository
from src.services.vpn_config import (
    build_subscription_payload,
    build_vless_link,
    build_vless_subscription_payload,
    build_xray_config,
    build_xray_config_json,
    sanitize_remark,
)

router = APIRouter()


def _subscription_userinfo(expires_at: datetime) -> str:
    expire_ts = int(expires_at.timestamp())
    return f"upload=0; download=0; total=0; expire={expire_ts}"


def _check_active(subscription) -> None:
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED):
        raise HTTPException(status_code=403, detail="Subscription inactive")
    if subscription.expires_at <= utcnow():
        raise HTTPException(status_code=403, detail="Subscription expired")


@router.get("/sub/{token}")
async def subscription_feed(
    token: str,
    format: str = Query(default="base64", alias="format"),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """VPN client subscription endpoint (Hiddify / v2rayNG / Streisand)."""
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)
    _check_active(subscription)

    user = subscription.user
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    remark = sanitize_remark(f"QooQ-VPN-{user.id}")

    headers = {
        "subscription-userinfo": _subscription_userinfo(subscription.expires_at),
        "profile-update-interval": "12",
        "profile-title": "QooQ VPN",
        "content-disposition": f'attachment; filename="qooq-{token[:8]}.txt"',
        "cache-control": "no-store",
    }

    if format == "json":
        return JSONResponse(
            content=build_xray_config(user.client_uuid, remark),
            headers=headers,
        )

    if format in ("profile", "xjson", "full"):
        payload = build_subscription_payload(user.client_uuid, remark)
        return PlainTextResponse(content=payload, media_type="text/plain; charset=utf-8", headers=headers)

    if format == "link":
        return PlainTextResponse(
            content=build_vless_link(user.client_uuid, remark) + "\n",
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    # default + format=vless + format=base64 — Happ / v2rayNG standard
    payload = build_vless_subscription_payload(user.client_uuid, remark)
    return PlainTextResponse(content=payload, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/sub/{token}/raw")
async def subscription_raw_json(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """Raw JSON config for debugging."""
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)
    _check_active(subscription)
    user = subscription.user
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    remark = sanitize_remark(f"QooQ-VPN-{user.id}")
    return Response(
        content=build_xray_config_json(user.client_uuid, remark),
        media_type="application/json",
        headers={
            "subscription-userinfo": _subscription_userinfo(subscription.expires_at),
        },
    )
