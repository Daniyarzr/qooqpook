import logging
import uuid
from decimal import Decimal

import httpx

from src.core.config import Settings

logger = logging.getLogger(__name__)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


class YooKassaError(Exception):
    pass


class YooKassaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.yookassa_enabled

    def _auth(self) -> tuple[str, str]:
        return self.settings.yookassa_shop_id, self.settings.yookassa_secret_key

    async def create_payment(
        self,
        amount: Decimal,
        order_id: int,
        user_id: int,
        description: str,
    ) -> dict:
        return_url = self.settings.yookassa_return_url
        if not return_url and self.settings.bot_username:
            return_url = f"https://t.me/{self.settings.bot_username}"

        payload = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url or "https://t.me/"},
            "capture": True,
            "description": description,
            "metadata": {"order_id": str(order_id), "user_id": str(user_id)},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{YOOKASSA_API_URL}/payments",
                json=payload,
                auth=self._auth(),
                headers={"Idempotence-Key": str(uuid.uuid4())},
            )

        if response.status_code >= 400:
            logger.error("YooKassa create payment failed: %s %s", response.status_code, response.text)
            raise YooKassaError(f"Payment creation failed: {response.status_code}")

        return response.json()

    async def get_payment(self, payment_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{YOOKASSA_API_URL}/payments/{payment_id}",
                auth=self._auth(),
            )

        if response.status_code >= 400:
            logger.error("YooKassa get payment failed: %s %s", response.status_code, response.text)
            raise YooKassaError(f"Payment fetch failed: {response.status_code}")

        return response.json()
