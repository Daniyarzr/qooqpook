"""Sync VPN server records in admin DB with production tunnel architecture."""

from __future__ import annotations

from sqlalchemy import select

from src.core.enums import ServerStatus
from src.models import VpnConfig, VpnServer
from src.services.vpn_config import (
    FINLAND_CONFIG_NAME,
    LTE_TUNNEL_CONFIG_NAME,
    LTE_XHTTP_CONFIG_NAME,
    PANEL_TUNNEL_HOST,
    PANEL_TUNNEL_PORT,
    VPN_HOST,
    VPN_PORT,
    VPN_SNI,
    export_finland_direct_json_template,
    export_lte_tunnel_json_template,
    export_lte_xhttp_json_template,
)


ENTRY_SERVER = {
    "name": "Yandex Entry (точка входа)",
    "country": "Russia",
    "country_flag": "🇷🇺",
    "host": VPN_HOST,
    "port": VPN_PORT,
    "protocol": "vless+tls",
    "max_users": 500,
    "sort_order": 0,
    "description": f"Клиенты подключаются сюда. SNI: {VPN_SNI}",
}

TUNNEL_SERVER = {
    "name": "Panel Tunnel (внутренний)",
    "country": "EU",
    "country_flag": "🔀",
    "host": PANEL_TUNNEL_HOST,
    "port": PANEL_TUNNEL_PORT,
    "protocol": "vless",
    "max_users": 500,
    "sort_order": 1,
    "description": "Внутренний hop — трафик с Yandex идёт сюда, дальше в интернет",
}


async def _upsert_server(session, spec: dict) -> VpnServer:
    result = await session.execute(
        select(VpnServer).where(VpnServer.host == spec["host"])
    )
    server = result.scalar_one_or_none()
    if server:
        server.name = spec["name"]
        server.country = spec["country"]
        server.country_flag = spec["country_flag"]
        server.port = spec["port"]
        server.protocol = spec["protocol"]
        server.max_users = spec["max_users"]
        server.sort_order = spec["sort_order"]
        server.is_active = True
        server.status = ServerStatus.ONLINE
        return server

    server = VpnServer(
        name=spec["name"],
        country=spec["country"],
        country_flag=spec["country_flag"],
        host=spec["host"],
        port=spec["port"],
        protocol=spec["protocol"],
        max_users=spec["max_users"],
        sort_order=spec["sort_order"],
        is_active=True,
        status=ServerStatus.ONLINE,
    )
    session.add(server)
    await session.flush()
    return server


async def _upsert_happ_config(
    session,
    *,
    server_id: int,
    name: str,
    template: str,
    is_default: bool,
    aliases: tuple[str, ...] = (),
) -> None:
    from src.core.enums import VpnConfigType

    result = await session.execute(
        select(VpnConfig)
        .where(
            VpnConfig.server_id == server_id,
            VpnConfig.name.in_((name, *aliases)),
        )
        .order_by(VpnConfig.id.desc())
    )
    configs = list(result.scalars().all())
    config = next((item for item in configs if item.name == name), None)
    if config is None and configs:
        config = configs[0]
    if config:
        config.name = name
        config.config_template = template
        config.config_type = VpnConfigType.XRAY_JSON
        config.is_active = True
        config.is_default = is_default
        return

    session.add(
        VpnConfig(
            server_id=server_id,
            name=name,
            config_type=VpnConfigType.XRAY_JSON,
            config_template=template,
            is_default=is_default,
            is_active=True,
        )
    )


async def sync_vpn_servers(session) -> list[str]:
    """Ensure admin server list matches real tunnel architecture."""
    messages: list[str] = []
    lte_template = export_lte_tunnel_json_template()
    finland_template = export_finland_direct_json_template()

    for spec in (ENTRY_SERVER, TUNNEL_SERVER):
        server = await _upsert_server(session, spec)
        messages.append(f"✅ Server synced: {server.name} ({server.host}:{server.port})")

    entry = await session.execute(select(VpnServer).where(VpnServer.host == VPN_HOST))
    entry_server = entry.scalar_one_or_none()
    panel = await session.execute(select(VpnServer).where(VpnServer.host == PANEL_TUNNEL_HOST))
    panel_server = panel.scalar_one_or_none()

    if entry_server:
        await _upsert_happ_config(
            session,
            server_id=entry_server.id,
            name=LTE_TUNNEL_CONFIG_NAME,
            template=lte_template,
            is_default=True,
            aliases=(
                "JSON-конфиг",
                "Основной",
                "Туннель LTE Обход 🇷🇺",
                "Xray JSON Profile",
            ),
        )
        messages.append(f"   ↳ Happ config: {LTE_TUNNEL_CONFIG_NAME}")
        await _upsert_happ_config(
            session,
            server_id=entry_server.id,
            name=LTE_XHTTP_CONFIG_NAME,
            template=export_lte_xhttp_json_template(),
            is_default=False,
            aliases=("LTE", "🇷🇺 LTE Обход"),
        )
        messages.append(f"   ↳ Happ config: {LTE_XHTTP_CONFIG_NAME}")

    if panel_server:
        await _upsert_happ_config(
            session,
            server_id=panel_server.id,
            name=FINLAND_CONFIG_NAME,
            template=finland_template,
            is_default=False,
            aliases=(
                "Финляндия QooQ VPN 🇫🇮",
                "Финляндия (QooQ)",
                "Финляндия 🇫🇮",
                "Финляндия Qooq Vpn",
            ),
        )
        messages.append(f"   ↳ Happ config: {FINLAND_CONFIG_NAME}")

    # Не трогаем пользовательские JSON из админки — только известный legacy-мусор
    legacy_names = {
        "Xray JSON Profile",
        "Туннель LTE Обход 🇷🇺",
        "Финляндия 🇫🇮",
        "Финляндия Qooq Vpn",
        "Германия 🇩🇪",
        "США 🇺🇸",
        "Австрия 🇦🇹",
        "Польша 🇵🇱",
    }
    result = await session.execute(select(VpnConfig))
    for legacy_config in result.scalars().all():
        if legacy_config.name in legacy_names:
            legacy_config.is_active = False
            legacy_config.is_default = False
            messages.append(f"   ↳ Deactivated legacy config: {legacy_config.name!r}")

    from src.services.config_credentials import ConfigCredentialService
    from src.core.config import get_settings

    revoked = await ConfigCredentialService(session, get_settings()).revoke_inactive_configs()
    if revoked:
        messages.append(f"   ↳ Revoked {revoked} stale credentials")

    # Deactivate obsolete demo servers pointing at wrong hosts
    result = await session.execute(select(VpnServer))
    known_hosts = {VPN_HOST, PANEL_TUNNEL_HOST}
    for legacy in result.scalars().all():
        if legacy.host not in known_hosts and (
            legacy.host.endswith("qooqvpn.ru") or legacy.name.startswith("Main Server")
        ):
            legacy.is_active = False
            if not legacy.name.startswith("[legacy]"):
                legacy.name = f"[legacy] {legacy.name}"
            messages.append(f"⚠️ Deactivated legacy server: {legacy.host}")

    return messages
