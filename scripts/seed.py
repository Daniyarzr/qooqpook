import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.admin.services import AdminService, hash_password
from src.core.config import get_settings
from src.db.session import async_session_factory
from src.models import AdminUser, SubscriptionPlan, VpnConfig, VpnServer


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
                sort_order=1,
            )
            session.add(server)
            await session.flush()

            config = VpnConfig(
                server_id=server.id,
                name="VLESS Reality",
                config_template="vless://{uuid}@{host}:{port}?type=tcp&security=reality#{name}",
            )
            session.add(config)
            print("✅ Demo VPN server created")

        await session.commit()
        print("\n🎉 Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
