import enum


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class SuspensionReason(str, enum.Enum):
    DEVICE_LIMIT = "device_limit"


class PromoDiscountType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    SUBSCRIPTION_PAYMENT = "subscription_payment"
    REFERRAL_BONUS = "referral_bonus"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class ServerStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class PaymentMethod(str, enum.Enum):
    BALANCE = "balance"
    YOOKASSA = "yookassa"
    TELEGRAM_STARS = "telegram_stars"
    CRYPTO = "crypto"
    MANUAL = "manual"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
