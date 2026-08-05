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
🔑 UUID: <code>{uuid}</code>
💰 Баланс: <b>{balance} ₽</b>
📎 Реф. код: <code>{referral_code}</code>
👥 Приглашено: <b>{referrals_count}</b>
📅 Регистрация: {created_at}
"""

SUBSCRIPTION_ACTIVE = """
✅ <b>Подписка активна</b>

📅 Действует до: <b>{expires_at}</b>
⏳ Осталось: <b>{duration}</b>
🔗 Ссылка: <code>{subscription_url}</code>

Скопируйте ссылку и добавьте в VPN-клиент.
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

REFERRAL = """
🎁 <b>Реферальная программа</b>

Приглашайте друзей и получайте бонусы!

🔗 Ваша ссылка:
<code>{referral_link}</code>

💰 Бонус: <b>{bonus_percent}%</b> от каждой покупки реферала
🎁 Дополнительно: <b>+{bonus_days} дней</b> к подписке

👥 Приглашено: <b>{referrals_count}</b>
💵 Заработано: <b>{earned} ₽</b>
"""

BALANCE = """
💰 <b>Ваш баланс</b>

Текущий баланс: <b>{balance} ₽</b>

Пополните баланс для оплаты подписок.
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
