import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.admin.services import AdminService, hash_password
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.core.enums import VpnConfigType
from src.models import AdminUser, SubscriptionPlan, VpnConfig, VpnServer
from src.services.vpn_config_store import VpnConfigStore, export_default_json_template


async def seed():
    settings = get_settings()

    async with async_session_factory() as session:
        # Admin user
        result = await session.execute(select(AdminUser).limit(1))
        if not result.scalar_one_or_none():
            admin = AdminUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_superadmin=True,
            )
            session.add(admin)
            print(f"✅ Admin created: {settings.admin_username}")

        # Subscription plans
        result = await session.execute(select(SubscriptionPlan).limit(1))
        if not result.scalar_one_or_none():
            plans = [
                SubscriptionPlan(
                    name="Стартовый",
                    description="Идеально для знакомства",
                    days=30,
                    price=Decimal("199.00"),
                    sort_order=1,
                ),
                SubscriptionPlan(
                    name="Стандарт",
                    description="Оптимальный выбор",
                    days=90,
                    price=Decimal("499.00"),
                    sort_order=2,
                ),
                SubscriptionPlan(
                    name="Премиум",
                    description="Максимальная выгода",
                    days=365,
                    price=Decimal("1499.00"),
                    sort_order=3,
                ),
            ]
            session.add_all(plans)
            print("✅ Subscription plans created")

        # Demo VPN server
        result = await session.execute(select(VpnServer).limit(1))
        if not result.scalar_one_or_none():
            server = VpnServer(
                name="Main Server",
                country="Germany",
                country_flag="🇩🇪",
                host=settings.hub_domain,
                port=10086,
                protocol="vless",
                max_users=50,
                sort_order=1,
            )
            session.add(server)
            await session.flush()

            config = VpnConfig(
                server_id=server.id,
                name="VLESS Reality",
                config_type=VpnConfigType.VLESS_LINK,
                config_template="vless://{uuid}@{host}:{port}?type=tcp&security=reality#{name}",
            )
            session.add(config)

            json_config = VpnConfig(
                server_id=server.id,
                name="Xray JSON Profile",
                config_type=VpnConfigType.XRAY_JSON,
                config_template=export_default_json_template(),
                is_default=True,
            )
            session.add(json_config)
            print("✅ Demo VPN server created")

        result = await session.execute(select(VpnServer))
        servers = list(result.scalars().all())
        store = VpnConfigStore(session)
        for server in servers:
            seeded = await store.seed_default_json_for_server(server.id)
            if seeded:
                print(f"✅ Default Xray JSON config for server {server.name}")

        await session.commit()
        print("\n🎉 Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
