# VPN: конфиги и обход RU-сайтов

## Как устроен туннель

```
Клиент (Happ / v2rayNG)
    ↓ VLESS + TLS, индивидуальный UUID
51.250.32.123:443  (white2.qooqvpn.ru, Yandex)
    ↓ Xray outbound (туннель)
148.135.184.188:10086  (Panel VPS)
    ↓ freedom
Интернет
```

Туннель — это **цепочка Xray-конфигов**, не WireGuard.

## Форматы подписки

| URL | Что получает клиент | RU-сайты напрямую |
|-----|---------------------|-------------------|
| `/sub/{token}` | VLESS-ссылка (base64) | ❌ Нет |
| `/sub/{token}?format=profile` | Полный JSON Xray (base64) | ✅ Да |
| `/sub/{token}?format=link` | VLESS текстом | ❌ Нет |
| `/sub/{token}?format=json` | JSON для отладки | ✅ Да |

### Почему два формата?

**Happ / v2rayNG** понимают подписку как `base64(vless://...)`.  
Правила маршрутизации (vk.ru, yandex.ru → direct) живут только в **полном JSON-профиле**.

- Для простого импорта в Happ — обычная ссылка из бота.
- Для обхода RU-сайтов — добавьте `?format=profile` или импортируйте JSON вручную.

## RU-обход в полном профиле

В `src/services/vpn_config.py` задано:

1. **DNS** — RU-домены резолвятся через `8.8.8.8` напрямую.
2. **Routing** — трафик на vk, yandex, gosuslugi, ozon и др. идёт в `direct` (минуя VPN).
3. **Остальной трафик** — через `proxy` (VLESS на Yandex).

Список доменов: `RU_DOMAINS` в `vpn_config.py`.

## Индивидуальный UUID и блокировка

- У каждого пользователя свой `client_uuid` в БД.
- UUID синхронизируется на Yandex inbound (`XRAY_SYNC_ENABLED=true`).
- При истечении подписки UUID удаляется с сервера — сохранённый конфиг перестаёт работать.

## Переменные для sync

```env
XRAY_SYNC_ENABLED=true
XRAY_SSH_HOST=51.250.32.123
XRAY_SSH_USER=adminka
XRAY_SSH_KEY_PATH=/root/.ssh/qooq_xray
XRAY_SSH_USE_SUDO=true
XRAY_CONFIG_PATH=/usr/local/etc/xray/config.json
XRAY_INBOUND_PORT=443
```

Первичная настройка ключа: `bash scripts/setup_xray_ssh.sh`
