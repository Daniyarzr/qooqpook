from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.core.config import Settings


def main_menu(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Моя подписка", callback_data="sub:status"),
                InlineKeyboardButton(text="💎 Тарифы", callback_data="sub:plans"),
            ],
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            ],
            [
                InlineKeyboardButton(text="🎁 Рефералы", callback_data="referral"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Mini App",
                    web_app=WebAppInfo(url=settings.webapp_url),
                ),
            ],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu:main")],
        ]
    )


def subscription_menu(
    has_subscription: bool,
    trial_used: bool,
    suspended_device_limit: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    if suspended_device_limit:
        buttons.append(
            [InlineKeyboardButton(text="📱 Устройства", callback_data="sub:devices")]
        )
        buttons.append(
            [InlineKeyboardButton(text="✅ Восстановить подписку", callback_data="sub:restore")]
        )
    elif not has_subscription and not trial_used:
        buttons.append(
            [InlineKeyboardButton(text="🎁 Пробный период", callback_data="sub:trial")]
        )
    elif has_subscription:
        buttons.append(
            [InlineKeyboardButton(text="📱 Устройства", callback_data="sub:devices")]
        )
        buttons.append(
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="sub:plans")]
        )
    else:
        buttons.append(
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="sub:plans")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def devices_keyboard(
    devices: list,
    can_add: bool,
    can_restore: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    for device in devices:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {device.name}",
                    callback_data=f"sub:device:del:{device.id}",
                )
            ]
        )
    if can_add:
        buttons.append(
            [InlineKeyboardButton(text="➕ Добавить устройство", callback_data="sub:device:add")]
        )
    if can_restore:
        buttons.append(
            [InlineKeyboardButton(text="✅ Восстановить подписку", callback_data="sub:restore")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ К подписке", callback_data="sub:status")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plans_keyboard(plans: list) -> InlineKeyboardMarkup:
    buttons = []
    emojis = ["🥉", "🥈", "🥇", "💎", "👑"]
    for i, plan in enumerate(plans):
        emoji = emojis[i] if i < len(emojis) else "⭐"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{emoji} {plan.name} — {plan.days}д / {plan.price}₽",
                    callback_data=f"sub:buy:{plan.id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sub:status")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_purchase(
    plan_id: int,
    plan_name: str,
    price,
    promo_id: int | None = None,
    final_price=None,
) -> InlineKeyboardMarkup:
    pay_price = final_price if final_price is not None else price
    if promo_id:
        confirm_data = f"sub:confirm:{plan_id}:{promo_id}"
    else:
        confirm_data = f"sub:confirm:{plan_id}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Оплатить {pay_price} ₽ с баланса",
                    callback_data=confirm_data,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Ввести промокод",
                    callback_data=f"sub:promo:{plan_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="sub:plans")],
        ]
    )


def balance_menu(topup_enabled: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if topup_enabled:
        buttons.append(
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="balance:topup")]
        )
    buttons.extend(
        [
            [InlineKeyboardButton(text="📜 История", callback_data="balance:history")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_amounts_keyboard(amounts: list[int]) -> InlineKeyboardMarkup:
    buttons = []
    row: list[InlineKeyboardButton] = []
    for amount in amounts:
        row.append(
            InlineKeyboardButton(
                text=f"{amount} ₽",
                callback_data=f"balance:topup:{amount}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="balance")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_payment_keyboard(order_id: int, payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"balance:check:{order_id}")],
            [InlineKeyboardButton(text="◀️ К балансу", callback_data="balance")],
        ]
    )
