"""Тексты бота — все сообщения в одном месте для удобства редактирования."""

WELCOME = """
🛡️ <b>Добро пожаловать в QooQ VPN!</b>

Быстрый, безопасный и надёжный VPN прямо в Telegram.

🔐 Индивидуальный доступ для каждого
🌍 Серверы по всему миру
⚡ Максимальная скорость
🎁 Реферальная программа

Выберите действие 👇
"""

WELCOME_BACK = """
👋 <b>С возвращением, {name}!</b>

Рады видеть вас снова. Чем могу помочь?
"""

PROFILE = """
👤 <b>Ваш профиль</b>

🆔 ID: <code>{telegram_id}</code>
🔑 UUID подписки: <code>{uuid}</code>
💰 Баланс: <b>{balance} ₽</b>
📎 Реф. код: <code>{referral_code}</code>
👥 Приглашено: <b>{referrals_count}</b>
📅 Регистрация: {created_at}
"""

SUBSCRIPTION_ACTIVE = """
✅ <b>Подписка активна</b>

📅 Действует до: <b>{expires_at}</b>
⏳ Осталось: <b>{duration}</b>
📱 Устройств: <b>{device_count}/{max_devices}</b>
🔗 Ссылка: <code>{subscription_url}</code>

Скопируйте ссылку и добавьте в VPN-клиент.
"""

DEVICES_HEADER = """
📱 <b>Ваши устройства</b> ({count}/{max_devices})

Каждое устройство имеет свой UUID. Обновите подписку в VPN-клиенте после изменений.

"""

DEVICES_ITEM = """
<b>{name}</b>
🔑 <code>{uuid}</code>
📊 Трафик: {traffic} GB
📅 {created}

"""

DEVICES_NONE = "Устройств пока нет."
DEVICES_LIMIT = "Достигнут лимит устройств ({max_devices}). Удалите одно, чтобы добавить новое."

SUBSCRIPTION_RESTORED = """
✅ <b>Подписка восстановлена!</b>

Доступ снова активен. Обновите подписку в VPN-клиенте.
"""

SUBSCRIPTION_SUSPENDED_DEVICES = """
⚠️ <b>Подписка приостановлена</b>

Обнаружено подключение <b>более {max_devices} устройств</b>. Разрешено не более {max_devices} на одну подписку.

Удалите лишние устройства и нажмите «✅ Восстановить подписку».
"""

SUBSCRIPTION_SUSPENDED = """
🔒 <b>Подписка приостановлена</b>

Обратитесь в поддержку для восстановления доступа.
"""

SUBSCRIPTION_EXPIRED = """
🔒 <b>Подписка не активна</b>

Ваш доступ приостановлен. Продлите подписку, чтобы снова пользоваться VPN.

💡 Если продлите до истечения — дни добавятся к текущей дате!
"""

SUBSCRIPTION_NONE = """
📭 <b>У вас нет активной подписки</b>

Оформите подписку или активируйте пробный период 🎁
"""

PLANS_HEADER = """
💎 <b>Тарифные планы</b>

Выберите подходящий тариф:
"""

PLAN_ITEM = """
{emoji} <b>{name}</b>
📅 {days} дней — <b>{price} ₽</b>
{description}
"""

TRIAL_ACTIVATED = """
🎁 <b>Пробный период активирован!</b>

📅 Действует <b>{days} дней</b> до {expires_at}
🔗 Ваша ссылка: <code>{subscription_url}</code>

Наслаждайтесь QooQ VPN! 🚀
"""

TRIAL_ALREADY_USED = """
⚠️ Вы уже использовали пробный период.

Оформите подписку в разделе «💎 Тарифы».
"""

EXTEND_SUCCESS = """
✅ <b>Подписка продлена!</b>

📅 Активна до: <b>{expires_at}</b>
⏳ Осталось: <b>{duration}</b>
🔗 Ссылка: <code>{subscription_url}</code>
"""

EXTEND_INSUFFICIENT_BALANCE = """
❌ <b>Недостаточно средств</b>

💰 Ваш баланс: <b>{balance} ₽</b>
💎 Стоимость: <b>{price} ₽</b>

Пополните баланс и попробуйте снова.
"""

PROMO_ASK = """
🎟 <b>Промокод</b>

Введите промокод сообщением в чат.

Тариф: <b>{plan_name}</b> — {price} ₽
"""

PROMO_APPLIED = """
🎟 <b>Промокод применён!</b>

Код: <code>{code}</code>
Скидка: <b>−{discount} ₽</b>
Итого: <b>{final_price} ₽</b>
"""

PROMO_INVALID = "❌ {error}"

REFERRAL = """
🎁 <b>Реферальная программа</b>

Приглашайте друзей по персональной ссылке — без промокодов!

🔗 Ваша ссылка:
<code>{referral_link}</code>

🎁 <b>−{discount_percent}%</b> за каждого приглашённого друга
👤 Друг получит <b>−{discount_percent}%</b> на первую покупку

👥 Приглашено: <b>{referrals_count}</b>
💡 Ваша текущая скидка: <b>{current_discount}%</b>
"""

REFERRAL_WELCOME = """
🎁 Вы перешли по реферальной ссылке!

На первую покупку подписки — скидка <b>{discount_percent}%</b>.
"""

BALANCE = """
💰 <b>Ваш баланс</b>

Текущий баланс: <b>{balance} ₽</b>

Пополните баланс для оплаты подписок через ЮKassa.
"""

DEPOSIT_NOT_CONFIGURED = "Пополнение временно недоступно. Обратитесь в поддержку."

DEPOSIT_CREATED = """
💳 <b>Счёт на оплату</b>

Сумма: <b>{amount} ₽</b>

Нажмите «Оплатить» и завершите платёж на странице ЮKassa.
После оплаты вернитесь в бот и нажмите «Проверить оплату».

🔗 <a href="{payment_url}">Ссылка на оплату</a>
"""

DEPOSIT_PENDING = "Оплата ещё не поступила. Подождите немного и проверьте снова."

DEPOSIT_SUCCESS = """
✅ <b>Баланс пополнен!</b>

💰 Зачислено: <b>{amount} ₽</b>
💳 Текущий баланс: <b>{balance} ₽</b>
"""

BALANCE_HISTORY_HEADER = """
📜 <b>История операций</b>

"""

BALANCE_HISTORY_ITEM = "{emoji} {amount} ₽ — {description}\n   📅 {date}\n"

HELP = """
❓ <b>Помощь</b>

<b>Как подключиться:</b>
1️⃣ Оформите подписку или активируйте trial
2️⃣ Скопируйте ссылку подписки
3️⃣ Добавьте в VPN-клиент (v2rayNG, Streisand, Hiddify)

<b>Поддерживаемые клиенты:</b>
📱 Android — v2rayNG, Hiddify
🍎 iOS — Streisand, Hiddify
💻 Windows — Hiddify, v2rayN
🐧 Linux — v2rayA, Hiddify

<b>Вопросы?</b> Напишите @support
"""

BANNED = """
🚫 <b>Доступ ограничен</b>

Ваш аккаунт заблокирован. Обратитесь в поддержку.
"""

PAYMENT_SUCCESS = """
✅ <b>Оплата прошла успешно!</b>

💰 Зачислено: <b>{amount} ₽</b>
💳 Баланс: <b>{balance} ₽</b>
"""
