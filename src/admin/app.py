from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.services import AdminService
from src.core.config import Settings, get_settings
from src.core.enums import SubscriptionStatus, VpnConfigType
from src.core.utils import build_subscription_url
from src.db.session import get_session
from src.models import Subscription

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

def _get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.admin_secret_key)


def create_admin_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="QooQ VPN Admin", docs_url=None, redoc_url=None, lifespan=lifespan)

    def get_current_admin(request: Request) -> str | None:
        token = request.cookies.get("admin_session")
        if not token:
            return None
        try:
            serializer = _get_serializer(settings)
            data = serializer.loads(
                token,
                max_age=settings.admin_session_expire_hours * 3600,
            )
            return data.get("username")
        except (BadSignature, SignatureExpired):
            return None

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if get_current_admin(request):
            return RedirectResponse("/dashboard", status_code=302)
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        session: AsyncSession = Depends(get_session),
    ):
        service = AdminService(session)
        admin = await service.authenticate(username, password)
        if not admin:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Неверный логин или пароль"},
                status_code=401,
            )

        serializer = _get_serializer(settings)
        token = serializer.dumps({"username": admin.username, "admin_id": admin.id})
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            "admin_session",
            token,
            httponly=True,
            max_age=settings.admin_session_expire_hours * 3600,
            samesite="lax",
        )
        return response

    @app.get("/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie("admin_session")
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        stats = await service.get_dashboard_stats()
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"admin": admin, "stats": stats},
        )

    @app.get("/users", response_class=HTMLResponse)
    async def users_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        users = await service.list_users()
        user_rows = [
            {"user": user, "subscription": AdminService.get_manageable_subscription(user)}
            for user in users
        ]
        return templates.TemplateResponse(
            request,
            "users.html",
            {"admin": admin, "user_rows": user_rows},
        )

    @app.get("/users/{user_id}", response_class=HTMLResponse)
    async def user_detail_page(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        user = await service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if settings.xray_stats_enabled:
            await service.sync_user_traffic(user_id, settings)

        subscription = AdminService.get_manageable_subscription(user)
        subscriptions_history = sorted(user.subscriptions, key=lambda s: s.created_at, reverse=True)
        transactions = sorted(user.transactions, key=lambda t: t.created_at, reverse=True)[:20]
        subscription_url = (
            build_subscription_url(settings.hub_domain, subscription.subscription_token)
            if subscription
            else None
        )
        devices = subscription.devices if subscription else []
        hwids = subscription.hwids if subscription else []
        device_limit_suspended = (
            subscription
            and subscription.status == SubscriptionStatus.SUSPENDED
            and subscription.suspension_reason == "device_limit"
        )

        return templates.TemplateResponse(
            request,
            "user_detail.html",
            {
                "admin": admin,
                "user": user,
                "subscription": subscription,
                "devices": devices,
                "hwids": hwids,
                "max_devices": settings.max_devices_per_subscription,
                "device_limit_suspended": device_limit_suspended,
                "subscriptions_history": subscriptions_history,
                "transactions": transactions,
                "traffic": AdminService.build_traffic_info(subscription),
                "subscription_url": subscription_url,
                "stats_enabled": settings.xray_stats_enabled,
            },
        )

    @app.post("/users/{user_id}/devices/add")
    async def add_device(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            await service.add_user_device(user_id, settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/devices/{device_id}/delete")
    async def delete_device(
        user_id: int,
        device_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.delete_user_device(user_id, device_id, settings)
        if not ok:
            raise HTTPException(status_code=404, detail="Device not found")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/hwids/clear")
    async def clear_hwids(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        await service.clear_user_hwids(user_id, settings)
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/subscription/reactivate")
    async def reactivate_subscription(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.reactivate_user_subscription(user_id, settings)
        if not ok:
            raise HTTPException(status_code=400, detail="Cannot reactivate subscription")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/ban")
    async def ban_user(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        await service.ban_user(user_id, banned=True)
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/unban")
    async def unban_user(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        await service.ban_user(user_id, banned=False)
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/subscription/deactivate")
    async def deactivate_subscription(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.deactivate_user_subscription(user_id, settings)
        if not ok:
            raise HTTPException(status_code=404, detail="Active subscription not found")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/subscription/delete")
    async def delete_subscription(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.delete_user_subscription(user_id, settings)
        if not ok:
            raise HTTPException(status_code=404, detail="Active subscription not found")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/subscription/extend")
    async def extend_subscription(
        user_id: int,
        request: Request,
        days: int = Form(...),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.extend_user_subscription(user_id, days, settings)
        if not ok:
            raise HTTPException(status_code=404, detail="Active subscription not found")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/balance/adjust")
    async def adjust_balance(
        user_id: int,
        request: Request,
        amount: Decimal = Form(...),
        description: str = Form(...),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        user = await service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await service.adjust_balance(user_id, amount, description)
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/traffic/sync")
    async def sync_traffic(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        await service.sync_user_traffic(user_id, settings)
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.post("/users/{user_id}/traffic/reset")
    async def reset_traffic(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        ok = await service.reset_user_traffic(user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Active subscription not found")
        return RedirectResponse(f"/users/{user_id}", status_code=302)

    @app.get("/plans", response_class=HTMLResponse)
    async def plans_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        plans = await service.list_plans()
        return templates.TemplateResponse(
            request,
            "plans.html",
            {"admin": admin, "plans": plans},
        )

    @app.get("/servers", response_class=HTMLResponse)
    async def servers_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        server_rows = await service.list_servers_with_stats()
        error = request.query_params.get("error")
        success = request.query_params.get("success")
        return templates.TemplateResponse(
            request,
            "servers.html",
            {
                "admin": admin,
                "server_rows": server_rows,
                "error": error,
                "success": success,
            },
        )

    @app.get("/servers/{server_id}", response_class=HTMLResponse)
    async def server_detail_page(
        server_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        server = await service.get_server_by_id(server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        stats = await service.get_server_stats(server)
        error = request.query_params.get("error")
        success = request.query_params.get("success")
        return templates.TemplateResponse(
            request,
            "server_detail.html",
            {
                "admin": admin,
                "server": server,
                "stats": stats,
                "error": error,
                "success": success,
                "capacity_hint": {
                    "ram_mb": 888,
                    "cpus": 1,
                    "recommended_max": 50,
                    "note": "Panel VPS: PostgreSQL, API, бот, админка, Nginx и Xray exit :10086",
                },
            },
        )

    @app.post("/servers/create")
    async def create_server(
        request: Request,
        name: str = Form(...),
        country: str = Form(...),
        host: str = Form(...),
        country_flag: str = Form("🌍"),
        port: int = Form(443),
        protocol: str = Form("vless"),
        max_users: int = Form(50),
        status: str = Form("online"),
        sort_order: int = Form(0),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            await service.create_server(
                name=name,
                country=country,
                host=host,
                country_flag=country_flag,
                port=port,
                protocol=protocol,
                max_users=max_users,
                status=status,
                sort_order=sort_order,
            )
        except ValueError as exc:
            return RedirectResponse(f"/servers?error={quote(str(exc))}", status_code=302)
        return RedirectResponse("/servers?success=created", status_code=302)

    @app.post("/servers/{server_id}/delete")
    async def delete_server(
        server_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            ok = await service.delete_server(server_id)
        except ValueError as exc:
            return RedirectResponse(f"/servers?error={quote(str(exc))}", status_code=302)
        if not ok:
            raise HTTPException(status_code=404, detail="Server not found")
        return RedirectResponse("/servers?success=deleted", status_code=302)

    @app.post("/servers/{server_id}/update")
    async def update_server(
        server_id: int,
        request: Request,
        name: str = Form(...),
        country: str = Form(...),
        host: str = Form(...),
        country_flag: str = Form("🌍"),
        port: int = Form(443),
        protocol: str = Form("vless"),
        max_users: int = Form(...),
        status: str = Form("online"),
        sort_order: int = Form(0),
        is_active: bool = Form(False),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            server = await service.update_server(
                server_id,
                name=name,
                country=country,
                country_flag=country_flag,
                host=host,
                port=port,
                protocol=protocol,
                max_users=max_users,
                status=status,
                sort_order=sort_order,
                is_active=is_active,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/servers/{server_id}?error={quote(str(exc))}",
                status_code=302,
            )
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        return RedirectResponse(f"/servers/{server_id}?success=1", status_code=302)

    @app.get("/configs", response_class=HTMLResponse)
    async def configs_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        config_rows = await service.list_configs_with_stats()
        servers = await service.list_servers()
        default_template = None
        try:
            from src.services.vpn_config_store import export_default_json_template

            default_template = export_default_json_template()
        except Exception:
            pass

        error = request.query_params.get("error")
        success = request.query_params.get("success")
        return templates.TemplateResponse(
            request,
            "configs.html",
            {
                "admin": admin,
                "config_rows": config_rows,
                "servers": servers,
                "default_template": default_template,
                "config_types": VpnConfigType,
                "error": error,
                "success": success,
            },
        )

    @app.get("/configs/{config_id}", response_class=HTMLResponse)
    async def config_detail_page(
        config_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        config = await service.get_config_by_id(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")

        subs_count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.config_id == config_id)
        )

        error = request.query_params.get("error")
        success = request.query_params.get("success")
        return templates.TemplateResponse(
            request,
            "config_detail.html",
            {
                "admin": admin,
                "config": config,
                "subscriptions_count": subs_count or 0,
                "error": error,
                "success": success,
            },
        )

    @app.post("/configs/create")
    async def create_config(
        request: Request,
        server_id: int = Form(...),
        name: str = Form(...),
        config_type: str = Form(...),
        config_template: str = Form(...),
        is_default: bool = Form(False),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            config = await service.create_vpn_config(
                server_id=server_id,
                name=name,
                config_type=config_type,
                config_template=config_template,
                is_default=is_default,
            )
        except ValueError as exc:
            return RedirectResponse(f"/configs?error={quote(str(exc))}", status_code=302)
        return RedirectResponse(f"/configs/{config.id}?success=created", status_code=302)

    @app.post("/configs/{config_id}/update")
    async def update_config(
        config_id: int,
        request: Request,
        name: str = Form(...),
        config_template: str = Form(...),
        is_default: bool = Form(False),
        is_active: bool = Form(False),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            config = await service.update_vpn_config(
                config_id,
                name=name,
                config_template=config_template,
                is_default=is_default,
                is_active=is_active,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/configs/{config_id}?error={quote(str(exc))}",
                status_code=302,
            )
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")
        return RedirectResponse(f"/configs/{config_id}?success=1", status_code=302)

    @app.post("/configs/{config_id}/delete")
    async def delete_config(
        config_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            ok = await service.delete_vpn_config(config_id)
        except ValueError as exc:
            return RedirectResponse(f"/configs?error={quote(str(exc))}", status_code=302)
        if not ok:
            raise HTTPException(status_code=404, detail="Config not found")
        return RedirectResponse("/configs?success=deleted", status_code=302)

    @app.get("/promo-codes", response_class=HTMLResponse)
    async def promo_codes_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        promo_codes = await service.list_promo_codes()
        plans = await service.list_plans()
        error = request.query_params.get("error")
        success = request.query_params.get("success")
        return templates.TemplateResponse(
            request,
            "promo_codes.html",
            {
                "admin": admin,
                "promo_codes": promo_codes,
                "plans": plans,
                "error": error,
                "success": success,
            },
        )

    @app.post("/promo-codes/create")
    async def create_promo_code(
        request: Request,
        code: str = Form(...),
        discount_type: str = Form(...),
        discount_value: Decimal = Form(...),
        description: str = Form(""),
        plan_id: str = Form(""),
        max_uses: str = Form(""),
        max_uses_per_user: int = Form(1),
        valid_until: str = Form(""),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)

        service = AdminService(session)
        parsed_plan_id = int(plan_id) if plan_id.strip() else None
        parsed_max_uses = int(max_uses) if max_uses.strip() else None
        parsed_valid_until = None
        if valid_until.strip():
            parsed_valid_until = datetime.fromisoformat(valid_until)
            if parsed_valid_until.tzinfo is None:
                parsed_valid_until = parsed_valid_until.replace(tzinfo=timezone.utc)

        try:
            await service.create_promo_code(
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                description=description.strip() or None,
                plan_id=parsed_plan_id,
                max_uses=parsed_max_uses,
                max_uses_per_user=max_uses_per_user,
                valid_until=parsed_valid_until,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/promo-codes?error={quote(str(exc))}",
                status_code=302,
            )
        return RedirectResponse("/promo-codes?success=created", status_code=302)

    @app.post("/promo-codes/{promo_id}/toggle")
    async def toggle_promo_code(
        promo_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        if not await service.toggle_promo_code(promo_id):
            raise HTTPException(status_code=404, detail="Promo code not found")
        return RedirectResponse("/promo-codes", status_code=302)

    @app.post("/promo-codes/{promo_id}/delete")
    async def delete_promo_code(
        promo_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        service = AdminService(session)
        try:
            ok = await service.delete_promo_code(promo_id)
        except ValueError as exc:
            return RedirectResponse(f"/promo-codes?error={quote(str(exc))}", status_code=302)
        if not ok:
            raise HTTPException(status_code=404, detail="Promo code not found")
        return RedirectResponse("/promo-codes?success=deleted", status_code=302)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ):
        admin = get_current_admin(request)
        if not admin:
            return RedirectResponse("/login", status_code=302)

        service = AdminService(session)
        referral_bonus = await service.get_referral_bonus_percent(settings)
        success = request.query_params.get("success")
        error = request.query_params.get("error")
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "admin": admin,
                "referral_bonus_percent": referral_bonus,
                "success": success,
                "error": error,
            },
        )

    @app.post("/settings/referral-bonus")
    async def update_referral_bonus(
        request: Request,
        referral_bonus_percent: int = Form(...),
        session: AsyncSession = Depends(get_session),
    ):
        if not get_current_admin(request):
            raise HTTPException(status_code=401)
        if referral_bonus_percent < 0 or referral_bonus_percent > 100:
            return RedirectResponse(
                f"/settings?error={quote('Процент должен быть от 0 до 100')}",
                status_code=302,
            )
        service = AdminService(session)
        await service.set_referral_bonus_percent(settings, referral_bonus_percent)
        return RedirectResponse("/settings?success=1", status_code=302)

    return app
