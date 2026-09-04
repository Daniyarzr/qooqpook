"""Xray / Happ JSON config builder."""

import base64
import copy
import json
import re
import uuid
from typing import Any
from urllib.parse import quote

# Yandex tunnel entry (TLS) -> forwards to panel Xray :10086
VPN_HOST = "51.250.32.123"
VPN_PORT = 443
VPN_SNI = "white2.qooqvpn.ru"
VPN_NETWORK = "tcp"
PANEL_TUNNEL_HOST = "148.135.184.188"
PANEL_TUNNEL_PORT = 10086

# LTE-обход (xHTTP) на :443 через SNI white.qooqvpn.ru (nginx ssl_preread).
# white2.qooqvpn.ru остаётся VLESS TCP для продакшен-клиентов.
LTE_XHTTP_PORT = 443
LTE_XHTTP_HOST = "white.qooqvpn.ru"
LTE_XHTTP_SNI = "white.qooqvpn.ru"
LTE_XHTTP_PATH = "/static/getFile/video/segment.ts"
LTE_XHTTP_MODE = "packet-up"
LTE_XHTTP_CONFIG_NAME = "🇷🇺 LTE"

SUBSCRIPTION_PROFILE_TITLE = "QOOQ VPN 🚀⚡"
SUBSCRIPTION_BOT_USERNAME = "qooqvpnbot"
SUBSCRIPTION_REMARK = "QOOQ VPN"
DEFAULT_REMARK = SUBSCRIPTION_REMARK
PLACEHOLDER_UUID = "{uuid}"
PLACEHOLDER_REMARKS = "{remarks}"

# RU sites that must bypass VPN (client → direct IP), иначе маркетплейсы видят зарубежный exit.
RU_DOMAINS = [
    "domain:vk.ru",
    "domain:vk.com",
    "domain:yandex.ru",
    "domain:yandex.net",
    "domain:yastatic.net",
    "domain:gosuslugi.ru",
    "domain:mail.ru",
    "domain:ok.ru",
    "domain:okcdn.ru",
    "domain:avito.ru",
    "domain:max.ru",
    "domain:oneme.ru",
    # Wildberries
    "domain:wildberries.ru",
    "domain:wb.ru",
    "domain:wbbasket.ru",
    "domain:wbstatic.net",
    "domain:wibes.ru",
    "domain:wb-cloud.ru",
    # Ozon
    "domain:ozon.ru",
    "domain:ozon.com",
    "domain:ozonusercontent.com",
    "domain:ozonru.me",
    "domain:ozon-st.ru",
]

# Shared UUID always present on Xray — expired users get Telegram-only via Happ routing.
EXPIRED_ANNOUNCE_UUID = uuid.UUID("c0ffee00-dead-4000-8000-00000000a001")
EXPIRED_ANNOUNCE_EMAIL = "qooq-announce-telegram"

# Instructional server names shown in Happ when subscription expired (like Freedom).
EXPIRED_MESSAGE_REMARKS = [
    "❌ Подписка закончилась",
    "Продлите её в Telegram-боте",
    "чтобы вернуть доступ",
    "🧢 Telegram бот",
]

# Domains/IPs that must go through VPN after expiry (Telegram MTProto uses IPs!).
# Do NOT use geoip:telegram / geosite:telegram — many Happ geoip.dat builds lack TELEGRAM.
HAPP_TELEGRAM_PROXY_SITES = [
    "domain:telegram.org",
    "domain:telegram.me",
    "domain:telegram.dog",
    "domain:t.me",
    "domain:tx.me",
    "domain:telesco.pe",
    "domain:tdesktop.com",
    "domain:telegra.ph",
    "domain:graph.org",
    "domain:cdn-telegram.org",
    "domain:telegram-cdn.org",
    "domain:api.telegram.org",
    "domain:core.telegram.org",
    "domain:web.telegram.org",
    "domain:desktop.telegram.org",
    "domain:kws1.telegram.org",
    "domain:kws2.telegram.org",
    "domain:kws3.telegram.org",
    "domain:kws4.telegram.org",
    "domain:qooqvpn.ru",
    "domain:app.qooqvpn.ru",
    "domain:keys.qooqvpn.ru",
]

HAPP_TELEGRAM_PROXY_IPS = [
    # Official Telegram DC / infra ranges (no geoip:telegram — missing in many .dat)
    "91.108.4.0/22",
    "91.108.8.0/22",
    "91.108.12.0/22",
    "91.108.16.0/22",
    "91.108.20.0/22",
    "91.108.36.0/23",
    "91.108.38.0/23",
    "91.108.56.0/22",
    "149.154.160.0/20",
    "185.76.151.0/24",
    "67.198.55.0/24",
    "95.161.64.0/20",
]

# Для Happ routing profile DirectSites (domain:…) + geo отдельно в DirectIp
HAPP_DIRECT_SITES = [
    "domain:wildberries.ru",
    "domain:wb.ru",
    "domain:wbbasket.ru",
    "domain:wbstatic.net",
    "domain:wibes.ru",
    "domain:wb-cloud.ru",
    "domain:ozon.ru",
    "domain:ozon.com",
    "domain:ozonusercontent.com",
    "domain:ozonru.me",
    "domain:ozon-st.ru",
    "domain:vk.ru",
    "domain:vk.com",
    "domain:yandex.ru",
    "domain:yandex.net",
    "domain:yastatic.net",
    "domain:gosuslugi.ru",
    "domain:mail.ru",
    "domain:ok.ru",
    "domain:avito.ru",
    "domain:max.ru",
]

XRAY_CONFIG_TEMPLATE: dict[str, Any] = {
    "dns": {
        "hosts": {
            "cloudflare-dns.com": "1.1.1.1",
            "dns.google": "8.8.8.8",
        },
        "queryStrategy": "UseIPv4",
        "servers": [
            "https://cloudflare-dns.com/dns-query",
            {
                "address": "https://cloudflare-dns.com/dns-query",
                "domains": [],
            },
            {
                "address": "8.8.8.8",
                "domains": RU_DOMAINS.copy(),
                "port": 53,
            },
        ],
    },
    "inbounds": [
        {
            "listen": "127.0.0.1",
            "port": 10808,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True, "userLevel": 8},
            "sniffing": {
                "destOverride": ["http", "tls", "quic"],
                "enabled": True,
            },
            "tag": "socks",
        },
        {
            "listen": "127.0.0.1",
            "port": 10809,
            "protocol": "http",
            "settings": {"userLevel": 8},
            "sniffing": {
                "destOverride": ["http", "tls", "quic"],
                "enabled": True,
            },
            "tag": "http",
        },
        {
            "listen": "127.0.0.1",
            "port": 11111,
            "protocol": "dokodemo-door",
            "settings": {"address": "127.0.0.1"},
            "tag": "metrics_in",
        },
    ],
    "log": {"loglevel": "warning"},
    "metrics": {"tag": "metrics_out"},
    "outbounds": [
        {
            "mux": {
                "concurrency": -1,
                "enabled": False,
                "xudpConcurrency": 8,
                "xudpProxyUDP443": "",
            },
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": VPN_HOST,
                        "port": VPN_PORT,
                        "users": [
                            {
                                "encryption": "none",
                                "id": "00000000-0000-0000-0000-000000000000",
                                "level": 8,
                                "security": "auto",
                            }
                        ],
                    }
                ]
            },
            "streamSettings": {
                "network": VPN_NETWORK,
                "security": "tls",
                "tcpSettings": {"header": {"type": "none"}},
                "tlsSettings": {
                    "allowInsecure": False,
                    "alpn": [],
                    "fingerprint": "",
                    "serverName": VPN_SNI,
                    "show": False,
                },
            },
            "tag": "proxy",
        },
        {
            "protocol": "freedom",
            "settings": {"domainStrategy": "UseIP"},
            "tag": "direct",
        },
        {
            "protocol": "blackhole",
            "settings": {"response": {"type": "http"}},
            "tag": "block",
        },
    ],
    "policy": {
        "levels": {
            "0": {"statsUserDownlink": True, "statsUserUplink": True},
            "8": {
                "connIdle": 300,
                "downlinkOnly": 1,
                "handshake": 4,
                "uplinkOnly": 1,
            },
        },
        "system": {
            "statsInboundDownlink": True,
            "statsInboundUplink": True,
            "statsOutboundDownlink": True,
            "statsOutboundUplink": True,
        },
    },
    "remarks": DEFAULT_REMARK,
    "routing": {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {"ip": ["1.1.1.1"], "outboundTag": "proxy", "port": 443},
            {"ip": ["8.8.8.8"], "outboundTag": "direct", "port": 53},
            {"inboundTag": ["metrics_in"], "outboundTag": "metrics_out"},
            {"domain": RU_DOMAINS.copy(), "outboundTag": "direct"},
            {"ip": ["135.181.131.58"], "outboundTag": "direct"},
        ],
    },
    "stats": {},
}

LTE_TUNNEL_CONFIG_NAME = "🇷🇺 Основной"
FINLAND_CONFIG_NAME = "🇫🇮 Финляндия (QooQ)"
LTE_TUNNEL_NAME_ALIASES = frozenset(
    {
        LTE_TUNNEL_CONFIG_NAME,
        LTE_XHTTP_CONFIG_NAME,
        "JSON-конфиг",
        "Основной",
        "Туннель LTE Обход 🇷🇺",
        "Xray JSON Profile",
        "🇷🇺 LTE",
        "LTE",
    }
)
FINLAND_NAME_ALIASES = frozenset(
    {
        FINLAND_CONFIG_NAME,
        "Финляндия QooQ VPN 🇫🇮",
        "Финляндия (QooQ)",
        "Финляндия 🇫🇮",
        "Финляндия Qooq Vpn",
    }
)


def export_lte_tunnel_json_template() -> str:
    """Yandex TLS entry — RU bypass routing, per-user UUID."""
    config = copy.deepcopy(XRAY_CONFIG_TEMPLATE)
    config["remarks"] = PLACEHOLDER_REMARKS
    config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = PLACEHOLDER_UUID
    return json.dumps(config, ensure_ascii=False, indent=2)


def export_lte_xhttp_json_template() -> str:
    """Yandex VLESS+xHTTP+TLS на :443 (SNI white.qooqvpn.ru) — обход LTE РФ."""
    config = {
        "remarks": PLACEHOLDER_REMARKS,
        "log": {"loglevel": "warning"},
        "dns": {
            "queryStrategy": "UseIPv4",
            "servers": ["1.1.1.1", "1.0.0.1"],
        },
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "tag": "socks",
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": LTE_XHTTP_HOST,
                            "port": LTE_XHTTP_PORT,
                            "users": [
                                {
                                    "encryption": "none",
                                    "id": PLACEHOLDER_UUID,
                                    "flow": "",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "xhttp",
                    "security": "tls",
                    "tlsSettings": {
                        "alpn": ["h2", "http/1.1"],
                        "fingerprint": "firefox",
                        "serverName": LTE_XHTTP_SNI,
                    },
                    "xhttpSettings": {
                        "host": LTE_XHTTP_SNI,
                        "mode": LTE_XHTTP_MODE,
                        "path": LTE_XHTTP_PATH,
                        "extra": {
                            "noSSEHeader": True,
                            "scMaxBufferedPosts": 30,
                            "uplinkHTTPMethod": "GET",
                            "xmux": {"maxConcurrency": "16-32"},
                        },
                    },
                },
                "tag": "proxy",
            },
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "outboundTag": "direct",
                    "domain": RU_DOMAINS.copy(),
                }
            ],
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


def export_finland_direct_json_template() -> str:
    """Direct VLESS to panel :10086 (Finland exit) + RU/WB/Ozon → direct."""
    config = {
        "remarks": PLACEHOLDER_REMARKS,
        "log": {"loglevel": "warning"},
        "dns": {
            "queryStrategy": "UseIPv4",
            "servers": [
                "1.1.1.1",
                {
                    "address": "8.8.8.8",
                    "domains": RU_DOMAINS.copy(),
                    "port": 53,
                },
            ],
        },
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
                "tag": "socks",
            },
            {
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http",
                "settings": {},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
                "tag": "http",
            },
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": PANEL_TUNNEL_HOST,
                            "port": PANEL_TUNNEL_PORT,
                            "users": [
                                {
                                    "encryption": "none",
                                    "id": PLACEHOLDER_UUID,
                                    "level": 8,
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "none",
                    "tcpSettings": {"header": {"type": "none"}},
                },
                "tag": "proxy",
            },
            {
                "protocol": "freedom",
                "settings": {"domainStrategy": "UseIP"},
                "tag": "direct",
            },
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "outboundTag": "direct",
                    "domain": RU_DOMAINS.copy(),
                },
                {
                    "type": "field",
                    "outboundTag": "direct",
                    "ip": ["geoip:private", "geoip:ru"],
                },
            ],
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


def _happ_routing_base(*, name: str, global_proxy: bool) -> dict[str, Any]:
    return {
        "Name": name,
        "GlobalProxy": global_proxy,
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoH",
        "DomesticDNSDomain": "https://dns.google/dns-query",
        "DomesticDNSIP": "8.8.8.8",
        "Geoipurl": (
            "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
        ),
        "Geositeurl": (
            "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
        ),
        "DnsHosts": {
            "cloudflare-dns.com": "1.1.1.1",
            "dns.google": "8.8.8.8",
        },
        "DirectSites": [],
        "DirectIp": [
            "geoip:private",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "169.254.0.0/16",
        ],
        "ProxySites": [],
        "ProxyIp": [],
        "BlockSites": [],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": False,
        "RouteOrder": "block-proxy-direct",
    }


def _encode_happ_routing_link(profile: dict[str, Any], *, activate: bool = True) -> str:
    encoded = base64.b64encode(
        json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    action = "onadd" if activate else "add"
    return f"happ://routing/{action}/{encoded}"


def build_happ_ru_direct_routing_link(*, activate: bool = True) -> str:
    """Happ subscription routing: WB/Ozon/RU → direct, остальное через выбранный сервер."""
    profile = _happ_routing_base(name="QooQ RU Direct", global_proxy=True)
    profile["DirectSites"] = HAPP_DIRECT_SITES.copy()
    profile["DirectIp"] = [
        "geoip:ru",
        "geoip:private",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
    ]
    return _encode_happ_routing_link(profile, activate=activate)


def build_happ_telegram_only_routing_link(*, activate: bool = True) -> str:
    """После истечения: через VPN только Telegram (домены + IP DC), остальное — direct."""
    profile = _happ_routing_base(name="QooQ Telegram Only", global_proxy=False)
    profile["ProxySites"] = HAPP_TELEGRAM_PROXY_SITES.copy()
    profile["ProxyIp"] = HAPP_TELEGRAM_PROXY_IPS.copy()
    # Prefer proxy match before direct so Telegram DC IPs are not leaked to ISP.
    profile["RouteOrder"] = "proxy-block-direct"
    return _encode_happ_routing_link(profile, activate=activate)

def build_xray_config(
    client_uuid: uuid.UUID,
    remark: str = DEFAULT_REMARK,
    template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if template is not None:
        from src.services.vpn_config_store import apply_json_template

        return apply_json_template(template, client_uuid, remark)

    config = copy.deepcopy(XRAY_CONFIG_TEMPLATE)
    config["remarks"] = sanitize_remark(remark)
    config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = str(client_uuid)
    return config


def build_xray_config_json(
    client_uuid: uuid.UUID,
    remark: str = DEFAULT_REMARK,
    template: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        build_xray_config(client_uuid, remark, template=template),
        ensure_ascii=False,
        indent=2,
    )


def build_subscription_payload(
    client_uuid: uuid.UUID,
    remark: str = DEFAULT_REMARK,
    template: dict[str, Any] | None = None,
) -> str:
    """Base64 full Xray JSON — RU site routing + individual UUID."""
    raw = json.dumps(
        build_xray_config(client_uuid, remark, template=template),
        ensure_ascii=False,
    )
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def sanitize_remark(remark: str) -> str:
    """Normalize server name for VLESS fragments and Xray remarks (UTF-8 safe)."""
    cleaned = remark.replace("\u2014", "-").replace("\u2013", "-")
    cleaned = cleaned.replace("\n", " ").replace("\r", " ").replace("#", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or SUBSCRIPTION_REMARK


def encode_vless_fragment(name: str) -> str:
    """URL-encoded name for VLESS link fragment (#name). Supports emoji."""
    return quote(name, safe="")


def encode_profile_title_header(title: str = SUBSCRIPTION_PROFILE_TITLE) -> str:
    """Happ: profile-title as base64 UTF-8 (latin-1 safe HTTP header)."""
    return f"base64:{base64.b64encode(title.encode('utf-8')).decode('ascii')}"


def get_vpn_architecture_info() -> dict[str, str | int]:
    return {
        "profile_title": SUBSCRIPTION_PROFILE_TITLE,
        "entry_host": VPN_HOST,
        "entry_port": VPN_PORT,
        "entry_sni": VPN_SNI,
        "tunnel_host": PANEL_TUNNEL_HOST,
        "tunnel_port": PANEL_TUNNEL_PORT,
    }


def build_vless_link(
    client_uuid: uuid.UUID,
    remark: str = DEFAULT_REMARK,
    *,
    host: str | None = None,
    port: int | None = None,
    sni: str | None = None,
    security: str | None = None,
) -> str:
    """VLESS share link.

    Без host — legacy LTE entry (Yandex TLS).
    С host панели / произвольным — берём их как есть (по умолчанию без TLS).
    """
    name = encode_vless_fragment(sanitize_remark(remark))
    if host is None:
        entry_host = VPN_HOST
        entry_port = port or VPN_PORT
        entry_security = security or "tls"
        entry_sni = sni if sni is not None else VPN_SNI
    else:
        entry_host = host
        entry_port = port if port is not None else PANEL_TUNNEL_PORT
        entry_security = security or ("tls" if entry_host == VPN_HOST else "none")
        entry_sni = sni if sni is not None else (VPN_SNI if entry_security == "tls" else "")

    params = [f"encryption=none", f"type={VPN_NETWORK}", "headerType=none"]
    if entry_security and entry_security != "none":
        params.append(f"security={entry_security}")
        if entry_sni:
            params.append(f"sni={entry_sni}")
    else:
        params.append("security=none")
    return f"vless://{client_uuid}@{entry_host}:{entry_port}?{'&'.join(params)}#{name}"


def build_vless_link_for_server(
    client_uuid: uuid.UUID,
    remark: str,
    *,
    host: str,
    port: int,
) -> str:
    """VLESS for a concrete server row — не подменяет адрес на Yandex."""
    if host == VPN_HOST:
        return build_vless_link(client_uuid, remark, host=host, port=port or VPN_PORT)
    return build_vless_link(
        client_uuid,
        remark,
        host=host,
        port=port,
        security="none",
        sni="",
    )


def extract_vless_endpoint(config_template: str) -> str | None:
    """address:port из outbound JSON — для UI, без привязки к vpn_servers."""
    try:
        data = json.loads(config_template)
    except (json.JSONDecodeError, TypeError):
        return None
    for outbound in data.get("outbounds", []):
        if outbound.get("protocol") != "vless":
            continue
        try:
            vnext = outbound["settings"]["vnext"][0]
            address = vnext.get("address")
            port = vnext.get("port")
            if address is not None and port is not None:
                return f"{address}:{port}"
        except (KeyError, IndexError, TypeError):
            continue
    return None

def build_vless_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    """Base64 vless share link for simple Happ import."""
    body = build_vless_link(client_uuid, remark) + "\n"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def build_multi_vless_subscription_payload(
    links: list[tuple],
) -> str:
    """links: (uuid, remark) или (uuid, remark, host, port)."""
    body = "".join(_link_from_tuple(item) + "\n" for item in links)
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def build_multi_vless_links_text(links: list[tuple]) -> str:
    return "".join(_link_from_tuple(item) + "\n" for item in links)


def _link_from_tuple(item: tuple) -> str:
    if len(item) >= 4:
        client_uuid, remark, host, port = item[0], item[1], item[2], item[3]
        return build_vless_link(client_uuid, remark, host=host, port=port)
    client_uuid, remark = item[0], item[1]
    return build_vless_link(client_uuid, remark)


def build_multi_share_links_payload(links: list[str]) -> str:
    """Base64 subscription body — each line is a separate Happ server entry."""
    body = "".join(line if line.endswith("\n") else f"{line}\n" for line in links if line.strip())
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def xray_config_to_vless_link(config: dict[str, Any], remark: str) -> str | None:
    """Build vless:// share link from Xray JSON outbound (foreign or template configs)."""
    for outbound in config.get("outbounds", []):
        if outbound.get("protocol") != "vless":
            continue
        try:
            vnext = outbound["settings"]["vnext"][0]
            user = vnext["users"][0]
            client_id = user["id"]
            address = vnext["address"]
            port = vnext["port"]
            stream = outbound.get("streamSettings") or {}
            network = stream.get("network", "tcp")
            security = stream.get("security") or "none"
            params: list[str] = ["encryption=none", f"type={network}"]

            if security and security != "none":
                params.append(f"security={security}")

            tls_settings = stream.get("tlsSettings") or {}
            reality_settings = stream.get("realitySettings") or {}
            sni = tls_settings.get("serverName") or reality_settings.get("serverName")
            if sni:
                params.append(f"sni={quote(str(sni), safe='')}")

            fp = (
                reality_settings.get("fingerprint")
                or tls_settings.get("fingerprint")
            )
            if fp:
                params.append(f"fp={quote(str(fp), safe='')}")

            alpn = tls_settings.get("alpn") or []
            if isinstance(alpn, list) and alpn:
                params.append(f"alpn={quote(','.join(str(x) for x in alpn), safe='')}")

            if security == "reality":
                pbk = reality_settings.get("publicKey")
                if pbk:
                    params.append(f"pbk={quote(str(pbk), safe='')}")
                sid = reality_settings.get("shortId")
                if sid:
                    params.append(f"sid={quote(str(sid), safe='')}")
                if not fp:
                    params.append("fp=chrome")

            if network == "ws":
                ws = stream.get("wsSettings") or {}
                path = (ws.get("path") or "/").strip() or "/"
                host = ws.get("host") or sni or address
                params.append(f"host={quote(str(host), safe='')}")
                params.append(f"path={quote(path, safe='')}")
            elif network == "grpc":
                grpc = stream.get("grpcSettings") or {}
                service_name = grpc.get("serviceName") or ""
                if service_name:
                    params.append(f"serviceName={quote(str(service_name), safe='')}")
            elif network in ("xhttp", "splithttp"):
                xhttp = stream.get("xhttpSettings") or stream.get("splithttpSettings") or {}
                path = (xhttp.get("path") or "/").strip() or "/"
                host = xhttp.get("host") or sni or address
                mode = xhttp.get("mode") or ""
                params.append(f"host={quote(str(host), safe='')}")
                params.append(f"path={quote(path, safe='')}")
                if mode:
                    params.append(f"mode={quote(str(mode), safe='')}")

            flow = user.get("flow")
            if flow:
                params.append(f"flow={quote(str(flow), safe='')}")

            name = encode_vless_fragment(sanitize_remark(remark))
            query = "&".join(params)
            return f"vless://{client_id}@{address}:{port}?{query}#{name}"
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return None


def xray_config_to_hysteria_link(config: dict[str, Any], remark: str) -> str | None:
    """Build hysteria2:// share link from Xray JSON hysteria outbound."""
    for outbound in config.get("outbounds", []):
        protocol = (outbound.get("protocol") or "").lower()
        if protocol not in ("hysteria", "hysteria2"):
            continue
        try:
            settings = outbound.get("settings") or {}
            stream = outbound.get("streamSettings") or {}
            hy = stream.get("hysteriaSettings") or {}
            tls = stream.get("tlsSettings") or {}

            address = settings.get("address")
            port = settings.get("port")
            auth = hy.get("auth") or settings.get("auth") or settings.get("password")
            if not address or not port or not auth:
                continue

            params: list[str] = []
            sni = tls.get("serverName") or address
            if sni:
                params.append(f"sni={quote(str(sni), safe='')}")
            alpn = tls.get("alpn") or []
            if isinstance(alpn, list) and alpn:
                params.append(f"alpn={quote(','.join(str(x) for x in alpn), safe='')}")
            fp = tls.get("fingerprint")
            if fp:
                params.append(f"fp={quote(str(fp), safe='')}")
            if tls.get("allowInsecure"):
                params.append("insecure=1")

            name = encode_vless_fragment(sanitize_remark(remark))
            query = "&".join(params)
            suffix = f"?{query}" if query else ""
            return f"hysteria2://{quote(str(auth), safe='')}@{address}:{port}{suffix}#{name}"
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return None


def xray_config_to_share_link(config: dict[str, Any], remark: str) -> str | None:
    """vless:// or hysteria2:// from full Xray JSON — без подмены на Yandex."""
    return (
        xray_config_to_vless_link(config, remark)
        or xray_config_to_hysteria_link(config, remark)
    )


def build_credential_share_link(
    client_uuid: uuid.UUID,
    config_type: str,
    config_template: str,
    remark: str,
) -> str:
    """One subscription line for Happ — name comes from config remark."""
    safe_remark = sanitize_remark(remark)

    if config_type == "vless_link":
        template = config_template.strip()
        link = template.replace(PLACEHOLDER_UUID, str(client_uuid)).replace("{uuid}", str(client_uuid))
        if "#" not in link:
            link = f"{link}#{encode_vless_fragment(safe_remark)}"
        return link

    from src.services.vpn_config_store import apply_json_template

    raw = config_template.strip()
    if PLACEHOLDER_UUID in raw or "{uuid}" in raw:
        applied = apply_json_template(raw, client_uuid, safe_remark)
    else:
        applied = json.loads(raw)
        applied["remarks"] = safe_remark

    # Always vless:// (or hy2) in mixed subscription — Happ ignores bare JSON lines.
    # RU/WB/Ozon bypass comes from happ://routing profile in the feed header/body.
    share = xray_config_to_share_link(applied, safe_remark)
    if share:
        return share
    raise ValueError(f"Не удалось собрать share-ссылку для конфига {safe_remark!r}")


EXPIRED_PLACEHOLDER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")
EXPIRED_SERVER_REMARK = "Podpiska-istekla-prodlite-v-Telegram"


def build_inactive_vless_link(remark: str = EXPIRED_SERVER_REMARK) -> str:
    """Non-working VLESS entry so Happ shows an expired notice in the server list."""
    name = encode_vless_fragment(sanitize_remark(remark))
    return f"vless://{EXPIRED_PLACEHOLDER_UUID}@127.0.0.1:1?encryption=none&security=none&type=tcp#{name}"


def build_inactive_subscription_payload(remark: str = EXPIRED_SERVER_REMARK) -> str:
    body = build_inactive_vless_link(remark) + "\n"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def build_expired_limited_share_links(
    config_type: str,
    config_template: str,
    *,
    remarks: list[str] | None = None,
    client_uuid: uuid.UUID | None = None,
) -> list[str]:
    """Happ feed for expired sub: telegram-only routing + instructional live profiles."""
    announce_uuid = client_uuid or EXPIRED_ANNOUNCE_UUID
    lines = [build_happ_telegram_only_routing_link(activate=True)]
    for remark in remarks or EXPIRED_MESSAGE_REMARKS:
        lines.append(
            build_credential_share_link(
                announce_uuid,
                config_type,
                config_template,
                remark,
            )
        )
    return lines


def build_expired_fallback_share_links(
    *,
    remarks: list[str] | None = None,
    client_uuid: uuid.UUID | None = None,
) -> list[str]:
    """Always-available expired feed via panel :10086 (no DB template needed)."""
    announce_uuid = client_uuid or EXPIRED_ANNOUNCE_UUID
    lines = [build_happ_telegram_only_routing_link(activate=True)]
    for remark in remarks or EXPIRED_MESSAGE_REMARKS:
        lines.append(
            build_vless_link_for_server(
                announce_uuid,
                remark,
                host=PANEL_TUNNEL_HOST,
                port=PANEL_TUNNEL_PORT,
            )
        )
    return lines


def build_expired_limited_subscription_payload(
    config_type: str,
    config_template: str,
) -> str:
    return build_multi_share_links_payload(
        build_expired_limited_share_links(config_type, config_template)
    )


def build_expired_telegram_xray_config(
    config_template: str,
    remark: str = "🧢 Telegram бот",
) -> dict[str, Any]:
    """Full JSON profile: proxy only Telegram/QooQ, block the rest."""
    from src.services.vpn_config_store import apply_json_template

    raw = config_template.strip()
    if PLACEHOLDER_UUID in raw or "{uuid}" in raw:
        config = apply_json_template(raw, EXPIRED_ANNOUNCE_UUID, sanitize_remark(remark))
    else:
        config = json.loads(raw)
        config["remarks"] = sanitize_remark(remark)
        for outbound in config.get("outbounds", []):
            if outbound.get("protocol") != "vless":
                continue
            try:
                outbound["settings"]["vnext"][0]["users"][0]["id"] = str(EXPIRED_ANNOUNCE_UUID)
            except (KeyError, IndexError, TypeError):
                continue

    telegram_domains = [
        "domain:telegram.org",
        "domain:telegram.me",
        "domain:t.me",
        "domain:telesco.pe",
        "domain:tdesktop.com",
        "domain:telegra.ph",
        "domain:api.telegram.org",
        "domain:core.telegram.org",
        "domain:web.telegram.org",
        "domain:qooqvpn.ru",
    ]
    telegram_ips = [
        "91.108.4.0/22",
        "91.108.8.0/22",
        "91.108.12.0/22",
        "91.108.16.0/22",
        "91.108.20.0/22",
        "91.108.36.0/23",
        "91.108.38.0/23",
        "91.108.56.0/22",
        "149.154.160.0/20",
        "185.76.151.0/24",
        "67.198.55.0/24",
        "95.161.64.0/20",
    ]
    config["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {
                "type": "field",
                "outboundTag": "proxy",
                "domain": telegram_domains,
            },
            {
                "type": "field",
                "outboundTag": "proxy",
                "ip": telegram_ips,
            },
            {
                "type": "field",
                "outboundTag": "direct",
                "ip": ["geoip:private"],
            },
            {
                "type": "field",
                "outboundTag": "block",
                "port": "0-65535",
            },
        ],
    }
    # Ensure proxy/direct/block tags exist
    tags = {o.get("tag") for o in config.get("outbounds", [])}
    if "direct" not in tags:
        config.setdefault("outbounds", []).append(
            {"protocol": "freedom", "tag": "direct", "settings": {}}
        )
    if "block" not in tags:
        config.setdefault("outbounds", []).append(
            {"protocol": "blackhole", "tag": "block"}
        )
    for outbound in config.get("outbounds", []):
        if outbound.get("protocol") == "vless" and not outbound.get("tag"):
            outbound["tag"] = "proxy"
    return config


def build_xray_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    return build_subscription_payload(client_uuid, remark)
