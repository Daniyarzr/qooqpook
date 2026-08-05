from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.db.session import get_session
from src.repositories import PlanRepository, UserRepository
from src.schemas import ExtendSubscriptionRequest, SubscriptionPlanRead, SubscriptionRead
from src.services import SubscriptionService

router = APIRouter()


@router.get("/plans", response_model=list[SubscriptionPlanRead])
async def list_plans(session: AsyncSession = Depends(get_session)):
    repo = PlanRepository(session)
    plans = await repo.get_active_plans()
    return plans


@router.get("/users/{telegram_id}/subscription", response_model=SubscriptionRead | None)
async def get_user_subscription(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    users = UserRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    service = SubscriptionService(session, settings)
    sub = await service.get_user_subscription(user.id)
    if not sub:
        return None

    from src.core.utils import build_subscription_url

    return SubscriptionRead(
        id=sub.id,
        status=sub.status,
        subscription_token=sub.subscription_token,
        started_at=sub.started_at,
        expires_at=sub.expires_at,
        is_trial=sub.is_trial,
        subscription_url=build_subscription_url(settings.hub_domain, sub.subscription_token),
        days_remaining=(sub.expires_at - sub.started_at).days,
    )


@router.post("/users/{telegram_id}/extend", response_model=SubscriptionRead)
async def extend_subscription(
    telegram_id: int,
    body: ExtendSubscriptionRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    users = UserRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")

    service = SubscriptionService(session, settings)
    try:
        sub = await service.extend_subscription(user.id, body.plan_id, body.payment_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    from src.core.utils import build_subscription_url

    return SubscriptionRead(
        id=sub.id,
        status=sub.status,
        subscription_token=sub.subscription_token,
        started_at=sub.started_at,
        expires_at=sub.expires_at,
        is_trial=sub.is_trial,
        subscription_url=build_subscription_url(settings.hub_domain, sub.subscription_token),
    )
