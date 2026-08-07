from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.core.enums import PaymentMethod, PaymentStatus, ServerStatus, SubscriptionStatus, TransactionType


class UserBase(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    client_uuid: UUID
    referral_code: str
    balance: Decimal
    is_active: bool
    is_banned: bool
    trial_used: bool
    created_at: datetime


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: SubscriptionStatus
    subscription_token: str
    client_uuid: UUID
    started_at: datetime
    expires_at: datetime
    is_trial: bool
    subscription_url: str | None = None
    days_remaining: int | None = None


class SubscriptionPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    days: int
    price: Decimal
    is_active: bool


class VpnServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str
    country_flag: str
    status: ServerStatus
    is_active: bool


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: TransactionType
    amount: Decimal
    balance_after: Decimal
    description: str | None
    payment_method: PaymentMethod | None
    created_at: datetime


class HubSubscriptionResponse(BaseModel):
    active: bool
    status: SubscriptionStatus
    expires_at: datetime | None
    expires_at_formatted: str | None
    duration_remaining: str | None
    subscription_url: str | None
    bot_link: str
    configs: list[str] = []
    message: str


class ExtendSubscriptionRequest(BaseModel):
    plan_id: int
    payment_method: PaymentMethod = PaymentMethod.BALANCE


class MiniAppDeviceRead(BaseModel):
    id: int
    name: str
    client_uuid: UUID
    traffic_gb: float
    created_at: datetime


class MiniAppSubscriptionRead(BaseModel):
    id: int
    status: SubscriptionStatus
    expires_at: datetime
    expires_at_formatted: str
    is_trial: bool
    subscription_url: str | None
    duration_remaining: str
    device_count: int
    max_devices: int
    suspended_device_limit: bool
    can_restore: bool
    hwid_count: int


class MiniAppReferralRead(BaseModel):
    referral_link: str
    referral_code: str
    bonus_percent: int
    referrals_count: int
    total_earned: Decimal


class MiniAppSettingsRead(BaseModel):
    trial_days: int
    max_devices: int
    deposit_amounts: list[int]
    yookassa_enabled: bool
    bot_username: str
    referral_welcome: bool = False


class MiniAppBootstrapResponse(BaseModel):
    user: UserRead
    subscription: MiniAppSubscriptionRead | None
    devices: list[MiniAppDeviceRead]
    plans: list[SubscriptionPlanRead]
    transactions: list[TransactionRead]
    referral: MiniAppReferralRead
    settings: MiniAppSettingsRead


class MiniAppPurchaseRequest(BaseModel):
    plan_id: int
    promo_code_id: int | None = None


class MiniAppPromoValidateRequest(BaseModel):
    code: str
    plan_id: int


class MiniAppPromoValidateResponse(BaseModel):
    promo_code_id: int
    code: str
    discount_amount: Decimal
    final_price: Decimal
    original_price: Decimal


class MiniAppDepositRequest(BaseModel):
    amount: Decimal


class MiniAppDepositResponse(BaseModel):
    order_id: int
    payment_url: str
    amount: Decimal
    status: PaymentStatus


class MiniAppDepositStatusResponse(BaseModel):
    order_id: int
    status: PaymentStatus
    balance: Decimal | None = None

