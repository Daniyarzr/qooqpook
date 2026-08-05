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


def subscription_menu(has_subscription: bool, trial_used: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not has_subscription and not trial_used:
        buttons.append(
            [InlineKeyboardButton(text="🎁 Пробный период", callback_data="sub:trial")]
        )
    if has_subscription:
        buttons.append(
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="sub:plans")]
        )
    else:
        buttons.append(
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="sub:plans")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
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


def confirm_purchase(plan_id: int, plan_name: str, price) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Оплатить {price} ₽ с баланса",
                    callback_data=f"sub:confirm:{plan_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="sub:plans")],
        ]
    )


def balance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 История", callback_data="balance:history")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
        ]
    )
