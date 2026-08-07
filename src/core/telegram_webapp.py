import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


@dataclass
class TelegramWebAppUser:
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None


@dataclass
class TelegramWebAppAuth:
    user: TelegramWebAppUser
    start_param: str | None
    auth_date: int


class TelegramWebAppError(ValueError):
    pass


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> TelegramWebAppAuth:
    if not init_data or not bot_token:
        raise TelegramWebAppError("Missing initData or bot token")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramWebAppError("Missing hash in initData")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramWebAppError("Invalid initData signature")

    auth_date = int(parsed.get("auth_date", 0))
    if max_age_seconds and time.time() - auth_date > max_age_seconds:
        raise TelegramWebAppError("initData expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise TelegramWebAppError("Missing user in initData")

    user_data = json.loads(user_raw)
    user = TelegramWebAppUser(
        id=int(user_data["id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
    )

    return TelegramWebAppAuth(
        user=user,
        start_param=parsed.get("start_param"),
        auth_date=auth_date,
    )
