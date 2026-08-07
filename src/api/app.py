from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import health, hub, miniapp, miniapp_api, payments, sub_feed, subscription
from src.core.config import get_settings

_STATIC_MINIAPP = Path(__file__).resolve().parent / "static" / "miniapp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_api_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="QooQ VPN API",
        description="API для mini-app, subscription hub и интеграций",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"]
            if settings.debug
            else [settings.webapp_url, settings.admin_url, f"https://{settings.hub_domain}"]
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(sub_feed.router, tags=["subscription-feed"])
    app.include_router(health.router, tags=["health"])
    app.include_router(miniapp.router, tags=["miniapp"])
    app.include_router(miniapp_api.router, tags=["miniapp-api"])
    app.include_router(hub.router, prefix="/hub", tags=["hub"])
    app.include_router(subscription.router, prefix="/api/v1", tags=["subscription"])
    app.include_router(payments.router, prefix="/api/v1", tags=["payments"])

    if _STATIC_MINIAPP.is_dir():
        app.mount(
            "/miniapp/static",
            StaticFiles(directory=_STATIC_MINIAPP),
            name="miniapp-static",
        )

    return app
