import base64

from enum import Enum



from fastapi import APIRouter, Depends, HTTPException, Query, Request

from fastapi.responses import JSONResponse, PlainTextResponse, Response

from sqlalchemy.ext.asyncio import AsyncSession



from src.core.config import Settings, get_settings

from src.core.enums import SubscriptionStatus, SuspensionReason, VpnConfigType

from src.core.utils import format_datetime_ru, utcnow

from src.db.session import get_session

from src.repositories import SubscriptionRepository

from src.services import SubscriptionService

from src.services.config_credentials import ConfigCredentialService

from src.services.device_limit import DeviceLimitService

from src.services.devices import DeviceService

from src.services.traffic_sync import get_traffic_limit_gb

from src.services.vpn_config import (

    EXPIRED_SERVER_REMARK,

    SUBSCRIPTION_BOT_USERNAME,

    SUBSCRIPTION_PROFILE_TITLE,

    SUBSCRIPTION_REMARK,

    build_inactive_subscription_payload,

    build_inactive_vless_link,

    build_multi_vless_links_text,

    build_multi_vless_subscription_payload,

    build_subscription_payload,

    build_vless_link,

    build_xray_config,

    build_xray_config_json,

    encode_profile_title_header,

    sanitize_remark,

)

from src.services.vpn_config_store import VpnConfigStore



router = APIRouter()





class InactiveReason(str, Enum):

    EXPIRED = "expired"

    DEVICE_LIMIT = "device_limit"

    SUSPENDED = "suspended"





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





def _bot_link(settings: Settings) -> str:

    username = settings.bot_username or SUBSCRIPTION_BOT_USERNAME

    return f"https://t.me/{username}"





def _encode_happ_text(text: str) -> str:

    return base64.b64encode(text.encode("utf-8")).decode("ascii")





def _credential_remark(credential) -> str:

    if credential.vpn_config and credential.vpn_config.name:

        return sanitize_remark(credential.vpn_config.name)

    device_name = credential.device.name if credential.device else "Device"

    return sanitize_remark(device_name)





def _build_active_headers(subscription, settings: Settings) -> dict[str, str]:

    bot = _bot_link(settings)

    expires = format_datetime_ru(subscription.expires_at)

    return {

        "subscription-userinfo": _subscription_userinfo(subscription),

        "profile-update-interval": "12",

        "profile-title": encode_profile_title_header(),

        "sub-expire": "1",

        "sub-expire-button-link": bot,

        "support-url": bot,

        "sub-info-color": "green",

        "sub-info-text": _encode_happ_text(f"Активна до: {expires}"),

        "sub-info-button-text": "Продлить",

        "sub-info-button-link": bot,

        "cache-control": "no-store",

    }





def _inactive_remark(reason: InactiveReason) -> str:

    if reason == InactiveReason.DEVICE_LIMIT:

        return "Podpiska-priostanovlena-limit-ustroystv"

    if reason == InactiveReason.SUSPENDED:

        return "Podpiska-neaktivna-prodlite-v-Telegram"

    return EXPIRED_SERVER_REMARK





def _inactive_profile_title(reason: InactiveReason) -> str:

    if reason == InactiveReason.DEVICE_LIMIT:

        return encode_profile_title_header("QOOQ VPN - limit")

    if reason == InactiveReason.SUSPENDED:

        return encode_profile_title_header("QOOQ VPN - inactive")

    return encode_profile_title_header("QOOQ VPN - expired")





def _inactive_info_text(reason: InactiveReason) -> str:

    if reason == InactiveReason.DEVICE_LIMIT:

        return (

            "Подписка приостановлена: превышен лимит устройств. "

            "Удалите лишние устройства и восстановите подписку в боте."

        )

    if reason == InactiveReason.SUSPENDED:

        return "Подписка неактивна. Продлите её в боте @qooqvpnbot"

    return "Ваша подписка закончилась. Продлите в боте @qooqvpnbot"





def _build_inactive_headers(subscription, settings: Settings, reason: InactiveReason) -> dict[str, str]:

    bot = _bot_link(settings)

    headers = {

        "subscription-userinfo": _subscription_userinfo(subscription),

        "profile-update-interval": "12",

        "profile-title": _inactive_profile_title(reason),

        "support-url": bot,

        "cache-control": "no-store",

        "content-disposition": 'attachment; filename="qooq-expired.txt"',

    }



    if reason == InactiveReason.EXPIRED:

        headers["sub-expire"] = "1"

        if bot:

            headers["sub-expire-button-link"] = bot

    else:

        headers["sub-info-color"] = "red"

        headers["sub-info-text"] = _encode_happ_text(_inactive_info_text(reason))

        headers["sub-info-button-text"] = "Продлить"

        if bot:

            headers["sub-info-button-link"] = bot



    return headers





def _build_inactive_response(

    subscription,

    settings: Settings,

    reason: InactiveReason,

    format: str,

) -> Response:

    headers = _build_inactive_headers(subscription, settings, reason)

    remark = _inactive_remark(reason)



    if format == "link":

        content = build_inactive_vless_link(remark) + "\n"

        return PlainTextResponse(

            content=content,

            media_type="text/plain; charset=utf-8",

            headers=headers,

        )



    if format in ("profile", "xjson", "full"):

        content = build_inactive_subscription_payload(remark)

        return PlainTextResponse(

            content=content,

            media_type="text/plain; charset=utf-8",

            headers=headers,

        )



    if format == "json":

        return JSONResponse(

            content={

                "remarks": SUBSCRIPTION_REMARK,

                "message": _inactive_info_text(reason),

                "active": False,

            },

            headers=headers,

        )



    content = build_inactive_subscription_payload(remark)

    return PlainTextResponse(

        content=content,

        media_type="text/plain; charset=utf-8",

        headers=headers,

    )





async def _resolve_inactive_reason(

    subscription,

    session: AsyncSession,

    settings: Settings,

    user,

    request: Request,

) -> InactiveReason | None:

    limit_service = DeviceLimitService(session, settings)

    suspended = await limit_service.check_and_enforce(subscription, user, request)

    if suspended:

        return InactiveReason.DEVICE_LIMIT



    if subscription.status == SubscriptionStatus.SUSPENDED:

        if subscription.suspension_reason == SuspensionReason.DEVICE_LIMIT.value:

            return InactiveReason.DEVICE_LIMIT

        await ConfigCredentialService(session, settings).revoke_subscription(subscription.id)

        await SubscriptionService(session, settings).sync_xray_clients()

        return InactiveReason.SUSPENDED



    if subscription.status == SubscriptionStatus.EXPIRED:

        await ConfigCredentialService(session, settings).revoke_subscription(subscription.id)

        await SubscriptionService(session, settings).sync_xray_clients()

        return InactiveReason.EXPIRED



    if subscription.expires_at <= utcnow():

        await SubscriptionService(session, settings).expire_subscription(subscription)

        return InactiveReason.EXPIRED



    return None





async def _get_vless_links(subscription, session, settings) -> list[tuple]:

    cred_service = ConfigCredentialService(session, settings)

    await cred_service.ensure_credentials(subscription)

    credentials = await cred_service.list_active(

        subscription.id, config_type=VpnConfigType.VLESS_LINK

    )

    if not credentials:

        credentials = await cred_service.list_active(

            subscription.id, config_type=VpnConfigType.XRAY_JSON

        )



    if credentials:

        return [

            (credential.client_uuid, _credential_remark(credential))

            for credential in credentials

        ]



    device_service = DeviceService(session, settings)

    devices = await device_service.list_devices(subscription.id)

    if not devices:

        devices = [await device_service.ensure_default_device(subscription)]

    return [(device.client_uuid, sanitize_remark(device.name)) for device in devices]





async def _get_profile_link(

    subscription,

    session,

    settings,

    vpn_config_id: int | None,

) -> tuple:

    cred_service = ConfigCredentialService(session, settings)

    await cred_service.ensure_credentials(subscription)



    if vpn_config_id:

        credentials = await cred_service.list_active(

            subscription.id, vpn_config_id=vpn_config_id

        )

    else:

        credentials = await cred_service.list_active(

            subscription.id, config_type=VpnConfigType.XRAY_JSON

        )



    if credentials:

        credential = credentials[0]

        return credential.client_uuid, _credential_remark(credential)



    device_links = await _get_vless_links(subscription, session, settings)

    return device_links[0]





@router.get("/sub/{token}")

async def subscription_feed(

    request: Request,

    token: str,

    format: str = Query(default="base64", alias="format"),

    session: AsyncSession = Depends(get_session),

    settings: Settings = Depends(get_settings),

):

    """VPN client subscription endpoint (Happ / v2rayNG / Streisand)."""

    repo = SubscriptionRepository(session)

    subscription = await repo.get_by_token(token)

    if not subscription:

        raise HTTPException(status_code=404, detail="Subscription not found")



    user = subscription.user

    if not user:

        raise HTTPException(status_code=404, detail="User not found")



    inactive_reason = await _resolve_inactive_reason(

        subscription, session, settings, user, request

    )

    if inactive_reason:

        return _build_inactive_response(subscription, settings, inactive_reason, format)



    config_store = VpnConfigStore(session)

    profile_config = await config_store.resolve_profile_config(subscription.config_id)

    profile_template = None

    if profile_config:

        profile_template = await config_store.get_profile_template(profile_config.id)



    headers = _build_active_headers(subscription, settings)

    headers["content-disposition"] = f'attachment; filename="qooq-{token[:8]}.txt"'



    if format == "json":

        client_uuid, remark = await _get_profile_link(

            subscription,

            session,

            settings,

            profile_config.id if profile_config else None,

        )

        return JSONResponse(

            content=build_xray_config(client_uuid, remark, template=profile_template),

            headers=headers,

        )



    if format in ("profile", "xjson", "full"):

        client_uuid, remark = await _get_profile_link(

            subscription,

            session,

            settings,

            profile_config.id if profile_config else None,

        )

        payload = build_subscription_payload(

            client_uuid, remark, template=profile_template

        )

        return PlainTextResponse(content=payload, media_type="text/plain; charset=utf-8", headers=headers)



    device_links = await _get_vless_links(subscription, session, settings)



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



    inactive_reason = await _resolve_inactive_reason(

        subscription, session, settings, user, request

    )

    if inactive_reason:

        return _build_inactive_response(subscription, settings, inactive_reason, "json")



    config_store = VpnConfigStore(session)

    profile_config = await config_store.resolve_profile_config(subscription.config_id)

    profile_template = await config_store.get_profile_template(

        profile_config.id if profile_config else subscription.config_id

    )



    client_uuid, remark = await _get_profile_link(

        subscription,

        session,

        settings,

        profile_config.id if profile_config else None,

    )



    headers = _build_active_headers(subscription, settings)

    return Response(

        content=build_xray_config_json(client_uuid, remark, template=profile_template),

        media_type="application/json",

        headers=headers,

    )


