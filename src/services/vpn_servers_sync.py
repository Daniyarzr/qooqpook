"""Sync VPN server records in admin DB with production tunnel architecture."""

from __future__ import annotations

from sqlalchemy import select

from src.core.enums import ServerStatus
from src.models import VpnConfig, VpnServer
from src.services.vpn_config import (
    PANEL_TUNNEL_HOST,
    PANEL_TUNNEL_PORT,
    VPN_HOST,
    VPN_PORT,
    VPN_SNI,
)
from src.services.vpn_config_store import VpnConfigStore, export_default_json_template


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


async def sync_vpn_servers(session) -> list[str]:
    """Ensure admin server list matches real tunnel architecture."""
    messages: list[str] = []
    store = VpnConfigStore(session)
    default_template = export_default_json_template()

    for spec in (ENTRY_SERVER, TUNNEL_SERVER):
        server = await _upsert_server(session, spec)
        messages.append(f"✅ Server synced: {server.name} ({server.host}:{server.port})")

        result = await session.execute(
            select(VpnConfig).where(VpnConfig.server_id == server.id)
        )
        configs = list(result.scalars().all())
        if server.host == VPN_HOST:
            from src.core.enums import VpnConfigType

            if not configs:
                session.add(
                    VpnConfig(
                        server_id=server.id,
                        name="Xray JSON Profile",
                        config_type=VpnConfigType.XRAY_JSON,
                        config_template=default_template,
                        is_default=True,
                        is_active=True,
                    )
                )
                messages.append(f"   ↳ JSON config created for {server.name}")
            else:
                for config in configs:
                    if config.config_type == VpnConfigType.XRAY_JSON:
                        config.config_template = default_template
                        config.is_default = True
                        messages.append(f"   ↳ JSON template updated for {server.name}")

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

    entry = await session.execute(select(VpnServer).where(VpnServer.host == VPN_HOST))
    entry_server = entry.scalar_one_or_none()
    if entry_server:
        await store.seed_default_json_for_server(entry_server.id)
    return messages
