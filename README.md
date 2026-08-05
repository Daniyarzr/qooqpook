# QooQ VPN (qooqpook)

VPN-платформа с продажей подписок через Telegram-бот, ссылкой-подписки для Happ/v2rayNG и админ-панелью.

Репозиторий: [github.com/Daniyarzr/qooqpook](https://github.com/Daniyarzr/qooqpook)

**Подробный обзор для разработчика:** [docs/WHAT_IS_DONE.md](docs/WHAT_IS_DONE.md)

---

## Что это и как работает (простыми словами)

1. Пользователь заходит в **Telegram-бот** → пополняет баланс или активирует trial → покупает подписку.
2. Бот выдаёт **индивидуальную ссылку** вида `https://keys.qooqvpn.ru/sub/{token}`.
3. Пользователь вставляет ссылку в **Happ** (или v2rayNG) → клиент получает VLESS-ключи (**отдельный UUID на каждое устройство**).
4. Трафик идёт по цепочке Xray-туннеля:

```
Телефон (Happ)
    ↓  VLESS + TLS, UUID пользователя
51.250.32.123:443  — Yandex, white2.qooqvpn.ru
    ↓  Xray outbound (туннель)
148.135.184.188:10086  — Panel VPS
    ↓  freedom
Интернет
```

5. Когда подписка **истекает** или **приостановлена**:
   - ссылка `/sub/{token}` перестаёт отдавать конфиг (403);
   - UUID **удаляются с Yandex** — сохранённый ключ не работает.

---

## Что уже сделано

### Backend (Python / FastAPI)
- [x] PostgreSQL + SQLAlchemy: пользователи, подписки, тарифы, баланс, устройства, промокоды
- [x] REST API для mini-app и hub
- [x] Subscription feed `/sub/{token}` — multi-device VLESS, HWID-контроль
- [x] Webhook ЮKassa `POST /api/v1/payments/yookassa/webhook`
- [x] Alembic миграции `001`–`008`
- [x] Docker Compose (PostgreSQL + Redis)

### Telegram-бот (aiogram 3)
- [x] Главное меню, trial, тарифы, оплата с баланса
- [x] **Пополнение баланса через ЮKassa**
- [x] **Промокоды** при покупке подписки
- [x] **Реферальная программа по ссылке** — автоматическая скидка (не промокод)
- [x] **Управление устройствами** (до 3 на подписку, свой UUID каждому)
- [x] Восстановление подписки после превышения лимита устройств
- [x] Профиль, баланс, история операций

### Админ-панель
- [x] **Dashboard** — финансы, пользователи, графики за 14 дней, последние операции
- [x] **Пользователи** — профиль, трафик, устройства, HWID, подписка, баланс
- [x] **Промокоды** — создание, вкл/выкл, удаление
- [x] **Серверы** — добавление/удаление, нагрузка, детальная страница
- [x] **Настройки** — % реферальной скидки
- [x] Бан/разбан, корректировка баланса, продление подписки

### VPN / Xray
- [x] **UUID на каждое устройство** подписки (не на пользователя)
- [x] Синхронизация UUID на Yandex (`51.250.32.123`) по SSH
- [x] **Лимит 3 устройства** — отслеживание HWID, автоприостановка + уведомление в Telegram
- [x] **Синхронизация трафика** через Xray Stats API (cron каждые 5 мин)
- [x] JSON-профиль с **обходом RU-сайтов** (vk, yandex, ozon → direct)
- [x] Cron: sync UUID + sync traffic

### Production (задеплоено)

| Домен | Назначение |
|-------|------------|
| `keys.qooqvpn.ru` | API + подписка `/sub/{token}` + hub |
| `admin.qooqvpn.ru` | Админ-панель |
| `app.qooqvpn.ru` | Telegram Mini App (базовая версия) |

| Сервер | IP | Роль | Ёмкость |
|--------|-----|------|---------|
| **Panel VPS** | `148.135.184.188` | API, бот, админка, PG, Xray `:10086` | ~**50** пользователей (888 MB RAM, 1 vCPU) |
| **Yandex** | `51.250.32.123` | Xray `:443` TLS — точка входа клиентов | — |

---

## Устройства и лимиты

| Лимит | Значение | Где настраивается |
|-------|----------|-------------------|
| Устройств на подписку | 3 | `MAX_DEVICES_PER_SUBSCRIPTION` в `.env` |
| HWID (уникальные клиенты) | 3 | автоматически при обращении к `/sub/{token}` |
| При превышении | SUSPENDED + Telegram-уведомление | — |
| Восстановление | Удалить лишние → «Восстановить подписку» в боте | — |

---

## Реферальная программа

- Ссылка: `https://t.me/{bot}?start=ref_{код}`
- **Приглашённый** — скидка на первую покупку
- **Пригласивший** — +N% скидки за каждого друга (суммируется, макс. 100%)
- Процент настраивается в админке: **⚙️ Настройки**
- Скидка применяется **автоматически**, без ввода промокода

---

## Промокоды

- Админка → **🎟 Промокоды**: процент или фиксированная сумма, лимит использований, срок, привязка к тарифу
- Бот → при покупке → **🎟 Ввести промокод**
- Если промокод выгоднее реферальной скидки — применяется он

---

## Форматы подписки

| URL | Для чего | RU-сайты напрямую |
|-----|----------|-------------------|
| `/sub/{token}` | Happ / v2rayNG (по умолчанию) | ❌ |
| `/sub/{token}?format=profile` | Полный JSON с routing | ✅ |
| `/sub/{token}?format=link` | VLESS текстом | ❌ |
| `/sub/{token}?format=json` | JSON для отладки | ✅ |

Подробнее: [docs/VPN.md](docs/VPN.md)

---

## Структура проекта

```
qooqpook/
├── src/
│   ├── core/           # config, enums, utils
│   ├── db/             # SQLAlchemy session
│   ├── models/         # User, Subscription, Device, PromoCode, ...
│   ├── repositories/   # доступ к БД
│   ├── services/       # subscription, payment, devices, promo, referral, traffic_sync, xray_sync
│   ├── api/            # FastAPI: hub, sub_feed, payments
│   ├── bot/            # Telegram-бот (handlers, keyboards, FSM)
│   └── admin/          # веб-админка (Jinja2)
├── alembic/versions/   # миграции 001–008
├── scripts/            # seed, redeploy, sync_xray_users, sync_traffic
├── docs/               # VPN.md, WHAT_IS_DONE.md
├── docker-compose.yml
├── run_api.py          # порт 8000
├── run_bot.py
└── run_admin.py        # порт 8001
```

---

## Быстрый старт (локально)

```bash
git clone https://github.com/Daniyarzr/qooqpook.git
cd qooqpook

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -e .
copy .env.example .env          # заполнить BOT_TOKEN и др.

docker compose up -d
alembic upgrade head
python scripts/seed.py

python run_api.py               # терминал 1
python run_bot.py               # терминал 2
python run_admin.py             # терминал 3
```

---

## Переменные окружения

Скопируйте `.env.example` → `.env`. Основное:

```env
BOT_TOKEN=...
BOT_USERNAME=qooqtestbot
DATABASE_URL=postgresql+asyncpg://qooq:...@localhost:5432/qooq_vpn
HUB_DOMAIN=keys.qooqvpn.ru
MAX_DEVICES_PER_SUBSCRIPTION=3

# Синхронизация UUID на Yandex
XRAY_SYNC_ENABLED=true
XRAY_SSH_HOST=51.250.32.123
XRAY_SSH_USER=adminka
XRAY_SSH_KEY_PATH=/root/.ssh/qooq_xray

# Статистика трафика (Xray Stats API)
XRAY_STATS_ENABLED=true
XRAY_STATS_API=127.0.0.1:10085

# ЮKassa
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_секретный_ключ
YOOKASSA_RETURN_URL=https://t.me/ваш_бот
DEPOSIT_AMOUNTS=100,300,500,1000,2000

# Реферальная скидка (дефолт; в prod — из админки → Настройки)
REFERRAL_DISCOUNT_PERCENT=10
```

**Не коммитьте `.env`** — он в `.gitignore`.

---

## Пополнение баланса (ЮKassa)

Пользователь: **💰 Баланс → 💳 Пополнить → сумма → оплата на странице ЮKassa**.

1. Webhook `POST /api/v1/payments/yookassa/webhook` зачисляет сумму
2. Уведомление в Telegram
3. Кнопка «🔄 Проверить оплату» — запасной вариант

### Настройка webhook

1. [личный кабинет ЮKassa](https://yookassa.ru/) → магазин
2. `.env`: `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_RETURN_URL`
3. HTTP-уведомления → `https://keys.qooqvpn.ru/api/v1/payments/yookassa/webhook`, событие `payment.succeeded`
4. `systemctl restart qooq-api qooq-bot`

---

## Деплой на VPS

```bash
set DEPLOY_PASSWORD=ваш_ssh_пароль
python scripts/redeploy.py
```

Скрипт: код → `/opt/qooq-vpn`, `pip install`, `alembic upgrade head`, перезапуск `qooq-api`, `qooq-admin`, `qooq-bot`.

Cron на сервере (автоматически):
- `sync_xray_users.py` — каждые 5 мин
- `sync_traffic.py` — каждые 5 мин

---

## Логика подписок

| Ситуация | Поведение |
|----------|-----------|
| Новая покупка | Подписка + token + UUID на каждое устройство |
| Продление (активна) | Дни **добавляются** к `expires_at` |
| Продление (истекла) | Отсчёт **с момента оплаты** |
| Истечение | EXPIRED, UUID сняты, `/sub/` → 403 |
| >3 HWID | SUSPENDED, уведомление в бот, восстановление вручную |
| Промокод / реферал | Скидка на оплату с баланса |

---

## Миграции БД

| Версия | Содержание |
|--------|------------|
| 001 | Базовая схема |
| 002 | Payment orders (ЮKassa) |
| 003 | UUID на подписку |
| 004 | Трафик (bytes на подписке и тарифе) |
| 005 | Устройства подписки |
| 006 | HWID + suspension_reason |
| 007 | Промокоды |
| 008 | system_settings + referral_discount_used |

```bash
alembic upgrade head
```

---

## Roadmap

- [x] Бот + API + админка
- [x] Subscription feed (VLESS + profile)
- [x] Xray UUID sync + multi-device
- [x] ЮKassa, промокоды, реферальные скидки
- [x] Лимит устройств + HWID
- [x] Dashboard с финансовой аналитикой
- [x] Управление серверами в админке
- [x] Синхронизация трафика
- [ ] Telegram Stars / крипто-оплата
- [ ] Mini-app (полноценный WebApp)
- [ ] Автовыбор формата подписки по User-Agent
- [ ] Multi-node балансировка (несколько Yandex-узлов)

---

## Совместная разработка

1. `git clone https://github.com/Daniyarzr/qooqpook.git`
2. `git checkout -b feature/название`
3. Коммит + push → Pull Request

Collaborators: **GitHub → Settings → Collaborators**

---

## Стек

Python 3.10+ · FastAPI · aiogram 3 · SQLAlchemy 2 · PostgreSQL · Redis · Alembic · Xray · Nginx · paramiko · YooKassa API

---

## Лицензия

Private / совместная разработка. Уточните у владельца репозитория.
