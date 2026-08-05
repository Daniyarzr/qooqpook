from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.core.config import get_settings

router = APIRouter()


@router.get("/miniapp", response_class=HTMLResponse)
@router.get("/miniapp/", response_class=HTMLResponse)
async def miniapp_page(request: Request):
    settings = get_settings()
    api_url = settings.api_base_url

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>QooQ VPN</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--tg-theme-bg-color, #0f0c29);
            color: var(--tg-theme-text-color, #fff);
            min-height: 100vh;
            padding: 20px 16px 32px;
        }}
        .header {{ text-align: center; margin-bottom: 28px; }}
        .logo {{ font-size: 52px; margin-bottom: 8px; }}
        h1 {{ font-size: 22px; font-weight: 700; }}
        .subtitle {{ color: var(--tg-theme-hint-color, #999); font-size: 14px; margin-top: 4px; }}
        .card {{
            background: var(--tg-theme-secondary-bg-color, rgba(255,255,255,0.08));
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 16px;
        }}
        .card-title {{ font-size: 13px; color: var(--tg-theme-hint-color, #999); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .status {{
            display: flex; align-items: center; gap: 10px;
            font-size: 18px; font-weight: 600;
        }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; background: #e74c3c; }}
        .dot.active {{ background: #2ecc71; box-shadow: 0 0 8px #2ecc71; }}
        .info-row {{
            display: flex; justify-content: space-between;
            padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.06);
            font-size: 14px;
        }}
        .info-row:last-child {{ border: none; }}
        .label {{ color: var(--tg-theme-hint-color, #999); }}
        .plans {{ display: flex; flex-direction: column; gap: 10px; }}
        .plan {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 14px 16px; border-radius: 14px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            cursor: pointer; transition: all 0.2s;
        }}
        .plan:active {{ transform: scale(0.98); background: rgba(102,126,234,0.2); }}
        .plan-name {{ font-weight: 600; }}
        .plan-price {{ color: #74b9ff; font-weight: 700; }}
        .loader {{ text-align: center; padding: 40px; color: #999; }}
        .btn {{
            display: block; width: 100%; padding: 16px;
            background: var(--tg-theme-button-color, linear-gradient(135deg, #667eea, #764ba2));
            color: var(--tg-theme-button-text-color, #fff);
            border: none; border-radius: 16px;
            font-size: 16px; font-weight: 600;
            cursor: pointer; margin-top: 8px;
        }}
        .btn:disabled {{ opacity: 0.5; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">🛡️</div>
        <h1>QooQ VPN</h1>
        <p class="subtitle">Быстрый и безопасный VPN</p>
    </div>

    <div id="content">
        <div class="loader">⏳ Загрузка...</div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        tg.setHeaderColor('#0f0c29');
        tg.setBackgroundColor('#0f0c29');

        const API = '{api_url}';
        const user = tg.initDataUnsafe?.user;

        async function load() {{
            if (!user) {{
                document.getElementById('content').innerHTML =
                    '<div class="card"><p style="text-align:center">Откройте через Telegram-бота 🤖</p></div>';
                return;
            }}

            try {{
                const [subRes, plansRes] = await Promise.all([
                    fetch(`${{API}}/api/v1/users/${{user.id}}/subscription`),
                    fetch(`${{API}}/api/v1/plans`),
                ]);
                const sub = subRes.ok ? await subRes.json() : null;
                const plans = plansRes.ok ? await plansRes.json() : [];

                let html = '';

                if (sub) {{
                    const exp = new Date(sub.expires_at);
                    const active = exp > new Date();
                    html += `<div class="card">
                        <div class="card-title">Подписка</div>
                        <div class="status">
                            <div class="dot ${{active ? 'active' : ''}}"></div>
                            ${{active ? '✅ Активна' : '🔒 Истекла'}}
                        </div>
                        <div class="info-row"><span class="label">До</span><span>${{exp.toLocaleDateString('ru')}}</span></div>
                        ${{sub.subscription_url ? `<div class="info-row"><span class="label">Ссылка</span><span style="font-size:11px;word-break:break-all">${{sub.subscription_url}}</span></div>` : ''}}
                    </div>`;
                }} else {{
                    html += `<div class="card">
                        <div class="status"><div class="dot"></div>🔒 Нет подписки</div>
                        <p style="margin-top:12px;font-size:14px;color:#999">Выберите тариф ниже</p>
                    </div>`;
                }}

                if (plans.length) {{
                    html += `<div class="card"><div class="card-title">💎 Тарифы</div><div class="plans">`;
                    for (const p of plans) {{
                        html += `<div class="plan" onclick="buyPlan(${{p.id}})">
                            <div><div class="plan-name">${{p.name}}</div><div style="font-size:12px;color:#999">${{p.days}} дней</div></div>
                            <div class="plan-price">${{p.price}} ₽</div>
                        </div>`;
                    }}
                    html += `</div></div>`;
                }}

                document.getElementById('content').innerHTML = html;
            }} catch (e) {{
                document.getElementById('content').innerHTML =
                    '<div class="card"><p style="text-align:center">❌ Ошибка загрузки</p></div>';
            }}
        }}

        function buyPlan(planId) {{
            tg.showAlert('Оформите подписку в боте 💎');
            tg.close();
        }}

        load();
    </script>
</body>
</html>"""
    )
