from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.services import AdminService
from src.core.config import Settings, get_settings
from src.db.session import get_session

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
        return templates.TemplateResponse(
            request,
            "users.html",
            {"admin": admin, "users": users},
        )

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
        return RedirectResponse("/users", status_code=302)

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
        return RedirectResponse("/users", status_code=302)

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
        servers = await service.list_servers()
        return templates.TemplateResponse(
            request,
            "servers.html",
            {"admin": admin, "servers": servers},
        )

    return app
