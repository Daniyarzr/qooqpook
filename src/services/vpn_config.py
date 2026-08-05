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
DEFAULT_REMARK = "QooQ VPN RU-Tunnel"

RU_DOMAINS = [
    "domain:vk.ru",
    "domain:yandex.ru",
    "domain:gosuslugi.ru",
    "domain:mail.ru",
    "domain:avito.ru",
    "domain:wildberries.ru",
    "domain:ozon.ru",
    "domain:yastatic.net",
    "domain:max.ru",
    "domain:okcdn.ru",
    "domain:oneme.ru",
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


def build_xray_config(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> dict[str, Any]:
    config = copy.deepcopy(XRAY_CONFIG_TEMPLATE)
    config["remarks"] = sanitize_remark(remark)
    config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = str(client_uuid)
    return config


def build_xray_config_json(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    return json.dumps(build_xray_config(client_uuid, remark), ensure_ascii=False, indent=2)


def sanitize_remark(remark: str) -> str:
    """VPN clients break on non-ASCII and special chars in link fragments."""
    cleaned = remark.replace("\u2014", "-").replace("\u2013", "-")
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s\-_.]", "", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-_ ")
    return cleaned or DEFAULT_REMARK


def build_vless_link(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    """VLESS TLS share link — Yandex tunnel entry."""
    name = quote(sanitize_remark(remark), safe="")
    params = (
        f"encryption=none&security=tls&sni={VPN_SNI}"
        f"&type={VPN_NETWORK}&headerType=none"
    )
    return f"vless://{client_uuid}@{VPN_HOST}:{VPN_PORT}?{params}#{name}"


def build_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    """Base64 full Xray JSON — RU site routing + individual UUID."""
    raw = json.dumps(build_xray_config(client_uuid, remark), ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def build_vless_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    """Base64 vless share link for simple Happ import."""
    body = build_vless_link(client_uuid, remark) + "\n"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def build_xray_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    return build_subscription_payload(client_uuid, remark)
