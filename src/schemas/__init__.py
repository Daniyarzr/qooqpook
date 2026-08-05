from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.core.enums import PaymentMethod, ServerStatus, SubscriptionStatus, TransactionType


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
