# QooQ VPN (qooqpook)

VPN-платформа с продажей подписок через Telegram-бот, ссылкой-подписки для Happ/v2rayNG и админ-панелью.

Репозиторий для совместной разработки: бэкенд, бот, генерация конфигов, синхронизация ключей на Xray-сервере.

**Подробный обзор для разработчика:** [docs/WHAT_IS_DONE.md](docs/WHAT_IS_DONE.md)

---

## Что это и как работает (простыми словами)

1. Пользователь заходит в **Telegram-бот** → покупает/активирует подписку.
2. Бот выдаёт **индивидуальную ссылку** вида `https://keys.qooqvpn.ru/sub/{token}`.
3. Пользователь вставляет ссылку в **Happ** (или v2rayNG) → клиент получает VLESS-ключ со **своим UUID**.
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

5. Когда подписка **истекает**:
   - ссылка `/sub/{token}` перестаёт отдавать конфиг (403);
   - UUID **удаляется с Yandex** — даже если кто-то сохранил ключ, он не работает.

---

## Что уже сделано

### Backend (Python / FastAPI)
- [x] PostgreSQL + SQLAlchemy модели: пользователи, подписки, тарифы, баланс, рефералы
- [x] REST API для mini-app и hub
- [x] Subscription feed `/sub/{token}` — выдача конфигов VPN-клиентам
- [x] Subscription Hub — красивая страница статуса подписки
- [x] Alembic миграции
- [x] Docker Compose (PostgreSQL + Redis)

### Telegram-бот (aiogram 3)
- [x] Главное меню, inline-кнопки
- [x] Trial-подписка, тарифы, оплата с баланса
- [x] **Пополнение баланса через ЮKassa** (карта, СБП и др.)
- [x] Профиль с UUID и реферальным кодом
- [x] Реферальные бонусы (% от покупки)
- [x] Ссылка на подписку для Happ

### Админ-панель
- [x] Авторизация (логин/пароль, bcrypt)
- [x] Dashboard, пользователи, тарифы, серверы
- [x] Бан/разбан пользователей

### VPN / Xray
- [x] Индивидуальный `client_uuid` на каждую подписку
- [x] Генерация VLESS-ссылки (формат для Happ)
- [x] Генерация полного JSON-профиля с **обходом RU-сайтов** (vk, yandex, ozon → direct)
- [x] Синхронизация UUID на Yandex (`51.250.32.123`) по SSH
- [x] Cron: блокировка истёкших подписок + обновление ключей на сервере
- [x] Продление подписки **от текущей даты окончания**, если ещё активна

### Production (задеплоено)
| Домен | Назначение |
|-------|------------|
| `keys.qooqvpn.ru` | API + подписка `/sub/{token}` + hub |
| `admin.qooqvpn.ru` | Админ-панель |
| `app.qooqvpn.ru` | Telegram Mini App (базовая версия) |

Серверы:
- **Panel VPS:** `148.135.184.188` — API, бот, админка, Xray `:10086` (приём туннеля)
- **Yandex:** `51.250.32.123` — Xray `:443` TLS (точка входа клиентов)

---

## Форматы подписки

| URL | Для чего | RU-сайты напрямую |
|-----|----------|-------------------|
| `/sub/{token}` | Happ / v2rayNG (по умолчанию) | ❌ |
| `/sub/{token}?format=profile` | Полный JSON с routing | ✅ |
| `/sub/{token}?format=link` | VLESS текстом | ❌ |
| `/sub/{token}?format=json` | JSON для отладки | ✅ |

Подробнее про VPN-конфиги: [docs/VPN.md](docs/VPN.md)

---

## Структура проекта

```
qooqpook/
├── src/
│   ├── core/           # config.py, enums, utils
│   ├── db/             # SQLAlchemy session
│   ├── models/         # User, Subscription, VpnServer, ...
│   ├── repositories/   # доступ к БД
│   ├── services/       # бизнес-логика, vpn_config, xray_sync
│   ├── api/            # FastAPI: hub, sub_feed, miniapp, payments
│   ├── bot/            # Telegram-бот
│   └── admin/          # веб-админка (Jinja2)
├── alembic/            # миграции
├── scripts/            # seed, deploy, sync_xray_users
├── docs/VPN.md         # документация по VPN
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

# Синхронизация UUID на Yandex
XRAY_SYNC_ENABLED=true
XRAY_SSH_HOST=51.250.32.123
XRAY_SSH_USER=adminka
XRAY_SSH_KEY_PATH=/root/.ssh/qooq_xray

# Пополнение баланса (ЮKassa)
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_секретный_ключ
YOOKASSA_RETURN_URL=https://t.me/ваш_бот
DEPOSIT_AMOUNTS=100,300,500,1000,2000
```

**Не коммитьте `.env`** — он в `.gitignore`.

---

## Пополнение баланса (ЮKassa)

Пользователь пополняет баланс в боте: **💰 Баланс → 💳 Пополнить → сумма → оплата на странице ЮKassa**.

После успешной оплаты:
1. Webhook `POST /api/v1/payments/yookassa/webhook` зачисляет сумму на баланс
2. Пользователь получает уведомление в Telegram
3. Кнопка «🔄 Проверить оплату» — запасной вариант, если webhook задержался

### Настройка

1. Создайте магазин в [личном кабинете ЮKassa](https://yookassa.ru/)
2. Добавьте в `.env` на сервере:
   - `YOOKASSA_SHOP_ID` — ID магазина
   - `YOOKASSA_SECRET_KEY` — секретный ключ API
   - `YOOKASSA_RETURN_URL` — куда вернуть пользователя после оплаты (обычно `https://t.me/имя_бота`)
3. В ЮKassa → **Интеграция → HTTP-уведомления** укажите URL:
   ```
   https://keys.qooqvpn.ru/api/v1/payments/yookassa/webhook
   ```
   Событие: `payment.succeeded`
4. Перезапустите API и бота: `systemctl restart qooq-api qooq-bot`

Для тестов используйте **тестовый** магазин и ключ с префиксом `test_`. Суммы пополнения задаются через `DEPOSIT_AMOUNTS` (по умолчанию 100–2000 ₽).

---

## Деплой на VPS

```bash
set DEPLOY_PASSWORD=ваш_ssh_пароль
python scripts/redeploy.py
```

Скрипт заливает код на `/opt/qooq-vpn`, ставит зависимости, мигрирует БД, перезапускает сервисы.

---

## Логика подписок

| Ситуация | Поведение |
|----------|-----------|
| Новая покупка | Создаётся подписка + token + UUID на Xray |
| Продление (активна) | Дни **добавляются** к `expires_at` |
| Продление (истекла) | Отсчёт **с момента оплаты** |
| Истечение | Статус EXPIRED, UUID снят с сервера, `/sub/` → 403 |
| Передача ключа другому | Работает пока активна подписка владельца; после — UUID удалён |

---

## Roadmap

- [x] Бот + API + админка
- [x] Subscription feed (VLESS + profile)
- [x] Xray UUID sync
- [x] RU-site bypass в profile-конфиге
- [x] Production deploy
- [x] Пополнение баланса через ЮKassa
- [ ] Telegram Stars / крипто-оплата
- [ ] Mini-app (полноценный WebApp)
- [ ] Вторая ссылка в боте «с обходом RU»
- [ ] Автовыбор формата подписки по User-Agent

---

## Совместная разработка

1. Клонировать репо
2. Создать ветку: `git checkout -b feature/название`
3. Коммит + push
4. Pull Request на GitHub

Добавить коллaborator: **GitHub → Settings → Collaborators**

---

## Стек

Python 3.10+ · FastAPI · aiogram 3 · SQLAlchemy 2 · PostgreSQL · Redis · Alembic · Xray · Nginx · paramiko

---

## Лицензия

Private / совместная разработка. Уточните у владельца репозитория.
