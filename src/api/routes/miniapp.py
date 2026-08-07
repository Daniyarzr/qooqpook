from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from src.core.config import get_settings

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "miniapp"
_INDEX_HTML = _STATIC_DIR / "index.html"
_VERSION = "4"


@router.get("/miniapp", response_class=HTMLResponse)
@router.get("/miniapp/", response_class=HTMLResponse)
async def miniapp_page():
    settings = get_settings()
    if settings.debug:
        api_prefix = f"{settings.api_base_url.rstrip('/')}/api/v1"
    else:
        api_prefix = "/api"

    html = _INDEX_HTML.read_text(encoding="utf-8")
    html = html.replace("{{API_PREFIX}}", api_prefix)
    html = html.replace("{{VERSION}}", _VERSION)
    return HTMLResponse(content=html)
