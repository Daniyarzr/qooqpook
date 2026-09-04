"""Short partner links: /p/{code} → Telegram bot deep link."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.utils import build_partner_bot_start
from src.db.session import get_session
from src.services.partners import PartnerService

router = APIRouter()


@router.get("/p/{code}")
async def partner_redirect(
    code: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    service = PartnerService(session)
    link = await service.record_click(code)
    if not link:
        raise HTTPException(status_code=404, detail="Partner link not found")

    bot_username = settings.bot_username or "qooqvpnbot"
    return RedirectResponse(
        build_partner_bot_start(bot_username, link.code),
        status_code=302,
    )
