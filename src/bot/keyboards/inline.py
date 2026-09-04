from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.core.config import Settings


def main_menu(settings: Settings, *, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
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
                text="📲 Как подключить VPN в приложение",
                callback_data="connect:guide",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🌐 Mini App",
                web_app=WebAppInfo(url=settings.webapp_url),
            ),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def to_main_menu_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    """Кнопка под сообщениями рассылки — открывает бота."""
    username = (settings.bot_username or "qooqvpnbot").lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 В главное меню",
                    url=f"https://t.me/{username}?start=menu",
                )
            ]
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Рассылка всем", callback_data="admin:broadcast:all")],
            [InlineKeyboardButton(text="👤 Рассылка одному", callback_data="admin:broadcast:one")],
            [InlineKeyboardButton(text="👥 Админы бота", callback_data="admin:admins")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]
    )


def admin_list_keyboard(admin_ids: list[int], root_ids: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for admin_id in admin_ids:
        label = f"{'🔒 ' if admin_id in root_ids else ''}{admin_id}"
        if admin_id in root_ids:
            rows.append([InlineKeyboardButton(text=label, callback_data="admin:admins:noop")])
        else:
            rows.append(
                [
                    InlineKeyboardButton(text=label, callback_data=f"admin:admins:remove:{admin_id}"),
                ]
            )
    rows.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:admins:add")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_broadcast_confirm_keyboard(scope: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"admin:broadcast:yes:{scope}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"admin:broadcast:no:{scope}"),
            ]
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu:main")],
        ]
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast:send"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
            ]
        ]
    )


def direct_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="dm:send"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="dm:cancel"),
            ]
        ]
    )


def subscription_menu(
    has_subscription: bool,
    trial_used: bool,
    suspended_device_limit: bool = False,
    *,
    expired: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    if suspended_device_limit:
        buttons.append(
            [InlineKeyboardButton(text="📱 Устройства", callback_data="sub:devices")]
        )
        buttons.append(
            [InlineKeyboardButton(text="✅ Восстановить подписку", callback_data="sub:restore")]
        )
    elif expired:
        buttons.append(
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="sub:plans")]
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
        buttons.append(
            [InlineKeyboardButton(text="🔐 Сбросить ссылку", callback_data="sub:reset")]
        )
    else:
        buttons.append(
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="sub:plans")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def devices_keyboard(
    devices: list | None = None,
    can_add: bool = False,
    can_restore: bool = False,
    hwids: list | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    # Реальные клиенты (HWID) — то, что считается в лимите
    for entry in hwids or []:
        label = getattr(entry, "label", None) or f"Устройство #{entry.id}"
        short = label if len(label) <= 28 else label[:27] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {short}",
                    callback_data=f"sub:hwid:del:{entry.id}",
                )
            ]
        )
    if can_restore:
        buttons.append(
            [InlineKeyboardButton(text="✅ Восстановить подписку", callback_data="sub:restore")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ К подписке", callback_data="sub:status")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка под сообщением рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


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
    balance=None,
    yookassa_enabled: bool = False,
) -> InlineKeyboardMarkup:
    pay_price = final_price if final_price is not None else price
    if promo_id:
        confirm_data = f"sub:confirm:{plan_id}:{promo_id}"
        yookassa_data = f"sub:pay:yookassa:{plan_id}:{promo_id}"
    else:
        confirm_data = f"sub:confirm:{plan_id}"
        yookassa_data = f"sub:pay:yookassa:{plan_id}"

    buttons = []
    can_balance = balance is not None and balance >= pay_price
    if can_balance:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"💰 Списать {pay_price} ₽ с баланса",
                    callback_data=confirm_data,
                )
            ]
        )
    if yookassa_enabled:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"💳 Оплатить {pay_price} ₽ (ЮKassa)",
                    callback_data=yookassa_data,
                )
            ]
        )
    if not can_balance and not yookassa_enabled:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Недостаточно средств ({pay_price} ₽)",
                    callback_data="balance",
                )
            ]
        )

    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="🎟 Ввести промокод",
                    callback_data=f"sub:promo:{plan_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="sub:plans")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def promo_error_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Попробовать ещё раз",
                    callback_data=f"sub:promo:retry:{plan_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Новый промокод",
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
    buttons.append(
        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="balance:topup:custom")]
    )
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


def reset_subscription_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="sub:reset:confirm")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="sub:status")],
        ]
    )
