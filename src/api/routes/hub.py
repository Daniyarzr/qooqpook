from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.db.session import get_session
from src.repositories import SubscriptionRepository
from src.schemas import HubSubscriptionResponse
from src.services import SubscriptionService

router = APIRouter()


@router.get("/sub/{token}", response_model=HubSubscriptionResponse)
async def get_subscription_hub(
    token: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    service = SubscriptionService(session, settings)
    data = service.build_hub_data(subscription, settings.bot_username)
    return HubSubscriptionResponse(**data)


@router.get("/sub/{token}/page", response_class=HTMLResponse)
async def subscription_hub_page(
    token: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_token(token)

    if not subscription:
        return HTMLResponse(
            content=_render_hub_page(
                title="QooQ VPN",
                status_text="❌ Подписка не найдена",
                active=False,
                bot_link=f"https://t.me/{settings.bot_username}",
            ),
            status_code=404,
        )

    service = SubscriptionService(session, settings)
    data = service.build_hub_data(subscription, settings.bot_username)

    status_emoji = "✅" if data["active"] else "🔒"
    status_text = f"{status_emoji} {data['message']}"

    expires_block = ""
    if data["expires_at_formatted"]:
        expires_block = f"""
        <div class="info-row">
            <span class="label">📅 Активна до</span>
            <span class="value">{data["expires_at_formatted"]}</span>
        </div>
        <div class="info-row">
            <span class="label">⏳ Осталось</span>
            <span class="value">{data["duration_remaining"]}</span>
        </div>
        """

    return HTMLResponse(
        content=_render_hub_page(
            title="QooQ VPN — Подписка",
            status_text=status_text,
            active=data["active"],
            bot_link=data["bot_link"],
            expires_block=expires_block,
            subscription_url=data["subscription_url"],
        )
    )


def _render_hub_page(
    title: str,
    status_text: str,
    active: bool,
    bot_link: str,
    expires_block: str = "",
    subscription_url: str | None = None,
) -> str:
    status_class = "active" if active else "expired"
    sub_url_block = ""
    if subscription_url and active:
        sub_url_block = f"""
        <div class="sub-url">
            <span class="label">🔗 Ссылка подписки</span>
            <code>{subscription_url}</code>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            padding: 20px;
        }}
        .card {{
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px 32px;
            max-width: 420px;
            width: 100%;
            border: 1px solid rgba(255,255,255,0.12);
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }}
        .logo {{ text-align: center; font-size: 48px; margin-bottom: 8px; }}
        h1 {{ text-align: center; font-size: 24px; margin-bottom: 24px; font-weight: 600; }}
        .status {{
            text-align: center;
            padding: 16px;
            border-radius: 16px;
            font-size: 18px;
            font-weight: 500;
            margin-bottom: 24px;
        }}
        .status.active {{ background: rgba(46, 204, 113, 0.2); border: 1px solid rgba(46, 204, 113, 0.4); }}
        .status.expired {{ background: rgba(231, 76, 60, 0.2); border: 1px solid rgba(231, 76, 60, 0.4); }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .label {{ color: rgba(255,255,255,0.6); font-size: 14px; }}
        .value {{ font-weight: 600; font-size: 14px; }}
        .sub-url {{
            margin-top: 20px;
            padding: 16px;
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
        }}
        .sub-url code {{
            display: block;
            margin-top: 8px;
            font-size: 11px;
            word-break: break-all;
            color: #74b9ff;
        }}
        .btn {{
            display: block;
            width: 100%;
            margin-top: 24px;
            padding: 16px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff;
            text-decoration: none;
            text-align: center;
            border-radius: 16px;
            font-size: 16px;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🛡️</div>
        <h1>QooQ VPN</h1>
        <div class="status {status_class}">{status_text}</div>
        {expires_block}
        {sub_url_block}
        <a href="{bot_link}" class="btn">🤖 Открыть бота</a>
    </div>
</body>
</html>"""
