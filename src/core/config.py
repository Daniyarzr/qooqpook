from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://qooq:qooq_secret@localhost:5432/qooq_vpn"
    database_url_sync: str = "postgresql://qooq:qooq_secret@localhost:5432/qooq_vpn"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Telegram
    bot_token: str = ""
    bot_username: str = ""
    admin_telegram_ids: Annotated[list[int], NoDecode] = []

    # Web
    webapp_url: str = "https://app.qooqvpn.ru"
    admin_url: str = "https://admin.qooqvpn.ru"
    hub_domain: str = "keys.qooqvpn.ru"
    api_base_url: str = "https://keys.qooqvpn.ru"

    # Admin
    admin_secret_key: str = "dev-secret-change-in-production"
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_session_expire_hours: int = 24

    # Subscription
    default_subscription_days: int = 30
    referral_bonus_percent: int = 10
    referral_bonus_days: int = 3
    trial_days: int = 3

    # Xray node (Reality inbound — per-user UUID sync)
    xray_sync_enabled: bool = False
    xray_ssh_host: str = "51.250.32.123"
    xray_ssh_port: int = 22
    xray_ssh_user: str = "adminka"
    xray_ssh_key_path: str = "/root/.ssh/qooq_xray"
    xray_ssh_use_sudo: bool = True
    xray_config_path: str = "/usr/local/etc/xray/config.json"
    xray_inbound_port: int = 443
    xray_reload_command: str = "systemctl restart xray"

    # App
    debug: bool = True
    environment: str = "development"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | list[int]) -> list[int]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [int(item.strip()) for item in str(value).split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
