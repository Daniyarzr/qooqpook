import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.db.session import get_session
from src.services.payment import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments")


@router.post("/yookassa/webhook")
async def yookassa_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.yookassa_enabled:
        return {"status": "disabled"}

    try:
        payload = await request.json()
    except Exception:
        return {"status": "invalid"}

    event = payload.get("event")
    payment_object = payload.get("object") or {}
    external_id = payment_object.get("id")

    if event != "payment.succeeded" or not external_id:
        return {"status": "ignored"}

    service = PaymentService(session, settings)
    order = await service.process_payment_success(external_id)
    if order:
        logger.info("Processed YooKassa payment %s for user %s", external_id, order.user_id)
        return {"status": "ok"}

    return {"status": "not_found"}
