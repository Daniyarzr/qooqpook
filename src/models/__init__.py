import uuid as uuid_std
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import (
    PaymentMethod,
    PaymentStatus,
    PromoDiscountType,
    ServerStatus,
    SubscriptionStatus,
    SuspensionReason,
    TransactionType,
)
from src.db.base import Base


def _enum(enum_cls):
    return Enum(enum_cls, values_callable=lambda items: [item.value for item in items])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_uuid: Mapped[uuid_std.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid_std.uuid4
    )
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    referral_discount_used: Mapped[bool] = mapped_column(Boolean, default=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    referred_by: Mapped["User | None"] = relationship(
        "User", remote_side="User.id", back_populates="referrals"
    )
    referrals: Mapped[list["User"]] = relationship("User", back_populates="referred_by")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )
    payment_orders: Mapped[list["PaymentOrder"]] = relationship(
        "PaymentOrder", back_populates="user", cascade="all, delete-orphan"
    )


class VpnServer(Base):
    __tablename__ = "vpn_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(64))
    country_flag: Mapped[str] = mapped_column(String(8), default="🌍")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(default=443)
    protocol: Mapped[str] = mapped_column(String(32), default="vless")
    status: Mapped[ServerStatus] = mapped_column(_enum(ServerStatus), default=ServerStatus.ONLINE)
    max_users: Mapped[int] = mapped_column(default=1000)
    current_users: Mapped[int] = mapped_column(default=0)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    configs: Mapped[list["VpnConfig"]] = relationship(
        "VpnConfig", back_populates="server", cascade="all, delete-orphan"
    )


class VpnConfig(Base):
    __tablename__ = "vpn_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("vpn_servers.id"))
    name: Mapped[str] = mapped_column(String(128))
    config_template: Mapped[str] = mapped_column(Text)
    inbound_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    server: Mapped["VpnServer"] = relationship("VpnServer", back_populates="configs")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="config"
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    days: Mapped[int] = mapped_column()
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    traffic_limit_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey("vpn_configs.id"), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_plans.id"), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        _enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    subscription_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    client_uuid: Mapped[uuid_std.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid_std.uuid4, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    bytes_upload: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_download: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_upload: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_download: Mapped[int] = mapped_column(BigInteger, default=0)
    last_traffic_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_limit_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    config: Mapped["VpnConfig | None"] = relationship("VpnConfig", back_populates="subscriptions")
    plan: Mapped["SubscriptionPlan | None"] = relationship("SubscriptionPlan")
    devices: Mapped[list["SubscriptionDevice"]] = relationship(
        "SubscriptionDevice",
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="SubscriptionDevice.created_at",
    )
    hwids: Mapped[list["SubscriptionHwid"]] = relationship(
        "SubscriptionHwid",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class SubscriptionHwid(Base):
    __tablename__ = "subscription_hwids"
    __table_args__ = (UniqueConstraint("subscription_id", "hwid", name="uq_subscription_hwid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    hwid: Mapped[str] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="hwids")


class SubscriptionDevice(Base):
    __tablename__ = "subscription_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[uuid_std.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid_std.uuid4
    )
    name: Mapped[str] = mapped_column(String(64), default="Устройство")
    bytes_upload: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_download: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_upload: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_download: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="devices")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[TransactionType] = mapped_column(_enum(TransactionType))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(_enum(PaymentMethod), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="transactions")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[PaymentStatus] = mapped_column(_enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="payment_orders")


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("referrer_id", "referred_id", name="uq_referral_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bonus_days: Mapped[int] = mapped_column(default=0)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount_type: Mapped[PromoDiscountType] = mapped_column(_enum(PromoDiscountType))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_plans.id"), nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped["SubscriptionPlan | None"] = relationship("SubscriptionPlan")
    redemptions: Mapped[list["PromoCodeRedemption"]] = relationship(
        "PromoCodeRedemption", back_populates="promo_code", cascade="all, delete-orphan"
    )


class PromoCodeRedemption(Base):
    __tablename__ = "promo_code_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    promo_code: Mapped["PromoCode"] = relationship("PromoCode", back_populates="redemptions")
    user: Mapped["User"] = relationship("User")
    subscription: Mapped["Subscription | None"] = relationship("Subscription")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
