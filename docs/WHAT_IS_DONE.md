# Что сделано в QooQ VPN — подробный обзор для разработчика

Этот файл — для того, кто подключается к проекию впервые. Здесь описано **что уже работает**, **как устроено**, **где что лежит в коде** и **что ещё не готово**.

Репозиторий: https://github.com/Daniyarzr/qooqpook

---

## 1. Идея проекта

**QooQ VPN** — сервис VPN-подписок:

- пользователь покупает/активирует подписку в **Telegram-боте**;
- получает **индивидуальную ссылку** на конфиг;
- вставляет её в **Happ** / v2rayNG;
- подключается к VPN через **цепочку Xray-серверов**;
- когда подписка кончается — ключ **перестаёт работать** (и на сервере, и по ссылке).

---

## 2. Production — что уже в бою

### Домены

| Домен | Что там |
|-------|---------|
| `keys.qooqvpn.ru` | API, подписка `/sub/{token}`, hub-страница |
| `admin.qooqvpn.ru` | Админ-панель |
| `app.qooqvpn.ru` | Telegram Mini App (базовая заготовка) |

### Серверы

| Сервер | IP | Роль |
|--------|-----|------|
| **Panel VPS** | `148.135.184.188` | API, бот, админка, PostgreSQL, Redis, Nginx, Xray `:10086` (принимает туннель) |
| **Yandex** | `51.250.32.123` | Xray `:443` TLS — **точка входа клиентов** (white2.qooqvpn.ru) |

SSH на Yandex: `ssh adminka@51.250.32.123`

### Как идёт трафик (важно!)

```
Клиент (Happ на телефоне)
    │
    │  VLESS + TLS, порт 443
    │  SNI: white2.qooqvpn.ru
    │  UUID — индивидуальный у каждого пользователя
    ▼
51.250.32.123  (Yandex Xray inbound)
    │
    │  Xray outbound → VLESS без TLS
    ▼
148.135.184.188:10086  (Panel Xray inbound)
    │
    │  outbound freedom
    ▼
Интернет
```

Туннель настроен **через Xray-конфиги**, не через WireGuard (WG на серверах есть, но VPN-трафик идёт по схеме выше).

### Telegram-бот

- Бот: `@qooqtestbot` (токен в `.env` на сервере, **не в репозитории**)

### Админка

- URL: https://admin.qooqvpn.ru
- Логин/пароль задаются в `.env` на сервере (`ADMIN_USERNAME`, `ADMIN_PASSWORD`)
- При первом деплое seed создаёт admin-пользователя в БД из этих переменных

---

## 3. Стек технологий

| Слой | Технология |
|------|------------|
| Язык | Python 3.10+ |
| API | FastAPI + Uvicorn |
| Бот | aiogram 3 |
| БД | PostgreSQL + SQLAlchemy 2 (async) |
| Миграции | Alembic |
| Кэш | Redis (подключён, использование минимальное) |
| Админка | FastAPI + Jinja2 |
| VPN | Xray (VLESS + TLS) |
| Деплой | systemd + Nginx + скрипты в `scripts/` |

---

## 4. Структура кода — где что искать

```
src/
├── core/
│   ├── config.py       ← все настройки из .env (Pydantic Settings)
│   ├── enums.py        ← статусы подписок, типы транзакций
│   └── utils.py        ← токены, URL подписки, формат дат
│
├── models/             ← ORM-модели PostgreSQL
│   User                ← telegram_id, client_uuid, balance, referral_code
│   Subscription        ← token, expires_at, status
│   SubscriptionPlan    ← тарифы (30/90/365 дней)
│   Transaction         ← история баланса
│   VpnServer, VpnConfig
│   AdminUser
│
├── repositories/       ← запросы к БД (без бизнес-логики)
├── services/
│   ├── __init__.py     ← SubscriptionService, BalanceService
│   ├── vpn_config.py   ← генерация VLESS и JSON-конфигов
│   └── xray_sync.py    ← синхронизация UUID на Yandex по SSH
│
├── api/
│   ├── app.py          ← FastAPI приложение
│   └── routes/
│       ├── sub_feed.py     ← GET /sub/{token} — выдача конфига клиенту
│       ├── hub.py          ← страница подписки + JSON hub
│       ├── subscription.py ← API для mini-app
│       └── miniapp.py      ← WebApp заготовка
│
├── bot/
│   ├── app.py          ← запуск бота
│   ├── handlers/       ← start, subscription, profile
│   ├── keyboards/      ← inline-кнопки
│   ├── middlewares/    ← DB session, Settings injection
│   └── texts/          ← все тексты сообщений
│
└── admin/
    ├── app.py          ← админ-панель
    ├── services.py     ← auth, stats
    └── templates/      ← HTML-шаблоны
```

Точки входа:

| Файл | Что запускает |
|------|---------------|
| `run_api.py` | API на порту 8000 |
| `run_bot.py` | Telegram-бот |
| `run_admin.py` | Админка на порту 8001 |

---

## 5. База данных — основные сущности

### User (пользователь)

- `telegram_id` — ID в Telegram (уникальный)
- `client_uuid` — **UUID для Xray**, генерируется один раз при регистрации, не меняется
- `balance` — баланс для оплаты подписок
- `referral_code` — код для реферальной ссылки
- `referred_by_id` — кто пригласил
- `trial_used` — использован ли пробный период

### Subscription (подписка)

- `subscription_token` — секретный токен в URL `/sub/{token}`
- `status` — ACTIVE / TRIAL / EXPIRED / SUSPENDED
- `expires_at` — дата окончания
- `user_id` — владелец

### Логика продления (`SubscriptionService.extend_subscription`)

1. Если подписка **ещё активна** → дни **добавляются** к `expires_at`
2. Если **истекла** → новый срок **от текущего момента**
3. После изменения → **sync UUID на Yandex**

---

## 6. Subscription feed — выдача конфигов клиентам

Файл: `src/api/routes/sub_feed.py`  
Файл конфигов: `src/services/vpn_config.py`

### Форматы URL

| Запрос | Ответ | Для чего |
|--------|-------|----------|
| `GET /sub/{token}` | base64(vless://...) | **По умолчанию.** Happ, v2rayNG |
| `GET /sub/{token}?format=profile` | base64(JSON Xray) | Полный профиль с RU-обходом |
| `GET /sub/{token}?format=link` | vless://... текстом | Ручной импорт |
| `GET /sub/{token}?format=json` | JSON | Отладка |

### Проверки перед выдачей

- подписка существует;
- статус не EXPIRED / SUSPENDED;
- `expires_at > now`.

Иначе → **403 Forbidden**.

### VLESS-ссылка (что видит Happ)

```
vless://{client_uuid}@51.250.32.123:443
  ?encryption=none
  &security=tls
  &sni=white2.qooqvpn.ru
  &type=tcp
  &headerType=none
  #{remark}
```

### Полный JSON-профиль (`?format=profile`)

Содержит:

- **DNS** — RU-домены резолвятся через 8.8.8.8 напрямую
- **Routing** — vk.ru, yandex.ru, ozon.ru, gosuslugi.ru и др. → `direct` (без VPN)
- **Outbound** — VLESS на 51.250.32.123 с UUID пользователя

Список RU-доменов: константа `RU_DOMAINS` в `vpn_config.py`.

> **Важно:** Happ по URL понимает только VLESS. Для RU-обхода нужен `?format=profile` или ручной импорт JSON.

---

## 7. Синхронизация UUID на Xray (блокировка ключей)

Файлы:

- `src/services/xray_sync.py` — логика
- `scripts/sync_xray_users.py` — cron-скрипт
- `scripts/setup_xray_ssh.sh` — настройка SSH-ключа

### Как работает

1. При активации/продлении подписки → `SubscriptionService.sync_xray_clients()`
2. Скрипт по SSH заходит на `51.250.32.123` под `adminka`
3. Читает `/usr/local/etc/xray/config.json`
4. В inbound `:443` обновляет список `clients`:
   - сохраняет чужие ключи (email не начинается с `qooq-`)
   - добавляет активных пользователей как `qooq-{user_id}` + их UUID
5. Перезапускает Xray

### Cron на panel-сервере

Каждые 5 минут:

```bash
python scripts/sync_xray_users.py
```

- помечает истёкшие подписки EXPIRED;
- обновляет UUID на Yandex.

### Переменные .env

```env
XRAY_SYNC_ENABLED=true
XRAY_SSH_HOST=51.250.32.123
XRAY_SSH_USER=adminka
XRAY_SSH_KEY_PATH=/root/.ssh/qooq_xray
XRAY_SSH_USE_SUDO=true
XRAY_CONFIG_PATH=/usr/local/etc/xray/config.json
XRAY_INBOUND_PORT=443
```

---

## 8. Telegram-бот — что умеет

| Функция | Файл | Статус |
|---------|------|--------|
| /start, регистрация | `handlers/start.py` | ✅ |
| Главное меню | `keyboards/inline.py` | ✅ |
| Trial (пробный период) | `services/__init__.py` | ✅ |
| Тарифы и оплата с баланса | `handlers/subscription.py` | ✅ |
| Ссылка на подписку | `core/utils.py` | ✅ |
| Профиль (UUID, реферал) | `handlers/profile.py` | ✅ |
| Реферальный бонус % | `services/__init__.py` | ✅ |
| Telegram Stars / крипта | — | ❌ не сделано |

### Middleware

- `middlewares/db.py` — сессия БД в каждый handler
- `middlewares/settings.py` — инъекция `Settings` (без этого бот не отвечал — была типичная ошибка)

---

## 9. Админ-панель

URL: https://admin.qooqvpn.ru

| Страница | Что делает |
|----------|------------|
| `/login` | Авторизация |
| `/dashboard` | Статистика (пользователи, активные подписки) |
| `/users` | Список пользователей, бан/разбан, UUID |
| `/plans` | Тарифы |
| `/servers` | VPN-серверы (из БД, пока demo) |

Seed создаёт 3 тарифа: 30 / 90 / 365 дней.

---

## 10. API эндпоинты (основные)

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/health` | Healthcheck |
| GET | `/sub/{token}` | Subscription feed для VPN-клиента |
| GET | `/sub/{token}/raw` | JSON конфиг (debug) |
| GET | `/hub/sub/{token}` | JSON статус подписки |
| GET | `/hub/sub/{token}/page` | HTML hub-страница |
| GET | `/api/subscription/{telegram_id}` | API для mini-app |

---

## 11. Деплой

### На сервере

Код лежит в `/opt/qooq-vpn`

Systemd-сервисы:

- `qooq-api` — FastAPI :8000
- `qooq-admin` — админка :8001
- `qooq-bot` — Telegram-бот

Nginx проксирует домены на эти порты + SSL (Let's Encrypt / acme.sh).

### Локальный деплой

```bash
set DEPLOY_PASSWORD=ssh-пароль
python scripts/redeploy.py
```

Скрипт: архив → upload → pip install → alembic → seed → restart.

**Пароли не хранятся в репозитории.** `DEPLOY_PASSWORD` передаётся через env.

---

## 12. Локальная разработка

```bash
git clone https://github.com/Daniyarzr/qooqpook.git
cd qooqpook

python -m venv .venv
.venv\Scripts\activate
pip install -e .

copy .env.example .env
# заполнить BOT_TOKEN, BOT_USERNAME, DATABASE_URL

docker compose up -d
alembic upgrade head
python scripts/seed.py

python run_api.py      # :8000
python run_bot.py
python run_admin.py    # :8001
```

---

## 13. Что НЕ сделано / TODO

| Задача | Приоритет | Комментарий |
|--------|-----------|-------------|
| Telegram Stars оплата | высокий | Сейчас только баланс |
| Крипто-оплата | средний | — |
| Mini-app WebApp | средний | Базовая страница есть, нужен UI |
| Вторая ссылка в боте «с RU-обходом» | средний | `?format=profile` |
| Автовыбор формата по User-Agent | низкий | Happ → vless, другие → profile |
| Marzban / 3X-UI интеграция | низкий | Сейчас прямое редактирование config.json |
| Тесты (pytest) | средний | Пока нет |
| CI/CD (GitHub Actions) | низкий | — |
| Ротация bot token | — | Токен светился в чатах — сменить |

---

## 14. Известные проблемы и решения (история)

| Проблема | Решение |
|----------|---------|
| Бот не отвечал | Не было `SettingsMiddleware` — добавлен |
| Subscription 404 | Роут был только `/hub/sub/`, добавлен `/sub/` в корень |
| Happ ошибка 39 | Подписка отдавала JSON вместо VLESS — исправлен default формат |
| «Удалённый хост закрыл соединение» | Большой JSON + кириллица в remark — вернули VLESS, ASCII-only имена |
| UUID не добавлялся на Yandex | Баг сравнения dict в xray_sync — исправлен deepcopy |
| WireGuard не используется для VPN | Туннель через Xray configs — документировано |

---

## 15. Файлы документации в репо

| Файл | Содержание |
|------|------------|
| `README.md` | Краткий обзор + быстрый старт |
| `docs/VPN.md` | VPN-конфиги, форматы, RU-обход |
| `docs/WHAT_IS_DONE.md` | **Этот файл** — полный обзор для разработчика |
| `.env.example` | Все переменные окружения |

---

## 16. Git workflow для двоих

```bash
git checkout -b feature/моя-задача
# ... правки ...
git add .
git commit -m "feat: описание"
git push origin feature/моя-задача
# Pull Request на GitHub
```

Ветка по умолчанию: `main`

**Не коммитить:** `.env`, пароли, SSH-ключи, bot token.

---

## 17. Быстрые команды на production (SSH panel)

```bash
# Логи API
journalctl -u qooq-api -f

# Логи бота
journalctl -u qooq-bot -f

# Перезапуск всего
systemctl restart qooq-api qooq-bot qooq-admin

# Ручной sync UUID
cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py

# Проверить подписку
curl -sk 'https://keys.qooqvpn.ru/sub/TOKEN?format=link'
```

## 18. Быстрые команды на Yandex

```bash
ssh adminka@51.250.32.123

sudo cat /usr/local/etc/xray/config.json   # список UUID
sudo systemctl status xray
sudo xray -test -config /usr/local/etc/xray/config.json
```

---

*Последнее обновление: август 2026. При изменениях в проекте — обновляй этот файл.*
