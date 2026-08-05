# 🛡️ QooQ VPN

VPN-платформа с подписками через Telegram-бот, mini-app и админ-панель.

## Архитектура

```
qooq_project/
├── src/
│   ├── core/           # Конфиг, enums, утилиты
│   ├── db/             # SQLAlchemy session, base
│   ├── models/         # ORM-модели (PostgreSQL)
│   ├── schemas/        # Pydantic-схемы
│   ├── repositories/   # Слой доступа к данным
│   ├── services/       # Бизнес-логика
│   ├── api/            # FastAPI REST API + Subscription Hub
│   ├── bot/            # Telegram-бот (aiogram 3)
│   │   ├── handlers/   # Обработчики команд
│   │   ├── keyboards/  # Inline-клавиатуры
│   │   ├── middlewares/# Middleware (DB session)
│   │   └── texts/      # Все тексты бота
│   └── admin/          # Админ-панель (FastAPI + Jinja2)
├── alembic/            # Миграции БД
├── scripts/            # Seed-скрипты
├── docker-compose.yml  # PostgreSQL + Redis
├── run_api.py          # Запуск API (порт 8000)
├── run_bot.py          # Запуск бота
└── run_admin.py        # Запуск админки (порт 8001)
```

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| **API** | 8000 | REST API, Subscription Hub, mini-app |
| **Bot** | — | Telegram-бот для пользователей |
| **Admin** | 8001 | Веб-панель администратора |
| **PostgreSQL** | 5432 | Основная БД |
| **Redis** | 6379 | Кэш, очереди (на будущее) |

## Быстрый старт (локально)

### 1. Поднять инфраструктуру

```bash
docker compose up -d
```

### 2. Установить зависимости

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .
```

### 3. Настроить окружение

```bash
copy .env.example .env
# Заполните BOT_TOKEN, BOT_USERNAME и другие переменные
```

### 4. Миграции и seed-данные

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
python scripts/seed.py
```

### 5. Запуск сервисов

```bash
# Терминал 1 — API
python run_api.py

# Терминал 2 — Бот
python run_bot.py

# Терминал 3 — Админка
python run_admin.py
```

## Функционал

### Telegram-бот
- 🛡️ Красивое главное меню с inline-кнопками
- 📱 Управление подпиской (статус, продление, trial)
- 💎 Тарифные планы с оплатой с баланса
- 👤 Профиль с UUID и реферальным кодом
- 💰 Баланс и история операций
- 🎁 Реферальная программа (бонус % от покупок)
- ❓ Справка по подключению

### Subscription Hub
- Красивая страница подписки по индивидуальной ссылке
- Показывает статус, дату окончания, оставшееся время
- 🔒 Блокировка при истечении подписки
- Ссылка на бота для продления

### Логика продления
- Если подписка **ещё активна** → дни добавляются к текущей дате окончания
- Если **истекла** → отсчёт с момента оплаты

### Админ-панель
- 📊 Dashboard со статистикой
- 👥 Управление пользователями (бан/разбан)
- 💎 Просмотр тарифов
- 🌍 Управление VPN-серверами
- 🔐 Авторизация по логину/паролю

### Subscription feed (VPN-клиенты)

- **По умолчанию** — VLESS для Happ / v2rayNG
- **`?format=profile`** — полный JSON с обходом RU-сайтов (vk, yandex, ozon → direct)

Подробнее: [docs/VPN.md](docs/VPN.md)

### UUID на Xray-сервере

- Синхронизация активных UUID на Yandex (`scripts/sync_xray_users.py`, cron)
- При истечении подписки ключ отключается на сервере

## GitHub / совместная разработка

```bash
git clone https://github.com/YOUR_USER/qooq-vpn.git
cd qooq-vpn
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
docker compose up -d
alembic upgrade head
python scripts/seed.py
```

Деплой на VPS (локально, нужен `DEPLOY_PASSWORD`):

```bash
set DEPLOY_PASSWORD=your-ssh-password
python scripts/redeploy.py
```

**Не коммитьте:** `.env`, пароли, bot token, SSH-ключи.

## Переменные окружения

Смотрите `.env.example` — все ключевые настройки там.

## Roadmap

- [x] Xray UUID sync на Yandex
- [x] Subscription feed (VLESS + profile)
- [ ] Telegram Stars / крипто-оплата
- [ ] Mini-app (Telegram WebApp)
- [ ] Автовыбор формата подписки по User-Agent клиента
