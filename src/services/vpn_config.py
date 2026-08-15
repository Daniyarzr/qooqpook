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

SUBSCRIPTION_PROFILE_TITLE = "QOOQ VPN 🚀⚡"
SUBSCRIPTION_BOT_USERNAME = "qooqvpnbot"
SUBSCRIPTION_REMARK = "QOOQ VPN"
DEFAULT_REMARK = SUBSCRIPTION_REMARK
PLACEHOLDER_UUID = "{uuid}"
PLACEHOLDER_REMARKS = "{remarks}"

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

LTE_TUNNEL_CONFIG_NAME = "JSON-конфиг"
FINLAND_CONFIG_NAME = "Финляндия QooQ VPN 🇫🇮"


def export_lte_tunnel_json_template() -> str:
    """Yandex TLS entry — RU bypass routing, per-user UUID."""
    config = copy.deepcopy(XRAY_CONFIG_TEMPLATE)
    config["remarks"] = PLACEHOLDER_REMARKS
    config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = PLACEHOLDER_UUID
    return json.dumps(config, ensure_ascii=False, indent=2)


def export_finland_direct_json_template() -> str:
    """Direct VLESS to panel Xray inbound (Finland exit)."""
    config = {
        "remarks": PLACEHOLDER_REMARKS,
        "log": {"loglevel": "warning"},
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
                "settings": {},
                "tag": "direct",
            },
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [],
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


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
) -> str:
    """VLESS TLS share link — Yandex tunnel entry."""
    name = encode_vless_fragment(sanitize_remark(remark))
    params = (
        f"encryption=none&security=tls&sni={entry_sni}"
        f"&type={VPN_NETWORK}&headerType=none"
    )
    return f"vless://{client_uuid}@{entry_host}:{entry_port}?{params}#{name}"


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

            if security == "reality":
                pbk = reality_settings.get("publicKey")
                if pbk:
                    params.append(f"pbk={quote(str(pbk), safe='')}")
                sid = reality_settings.get("shortId")
                if sid:
                    params.append(f"sid={quote(str(sid), safe='')}")
                fp = reality_settings.get("fingerprint") or "chrome"
                params.append(f"fp={fp}")

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

            flow = user.get("flow")
            if flow:
                params.append(f"flow={quote(str(flow), safe='')}")

            name = encode_vless_fragment(sanitize_remark(remark))
            query = "&".join(params)
            return f"vless://{client_id}@{address}:{port}?{query}#{name}"
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return None


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

    vless = xray_config_to_vless_link(applied, safe_remark)
    if vless:
        return vless
    return build_vless_link(client_uuid, safe_remark)


EXPIRED_PLACEHOLDER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")
EXPIRED_SERVER_REMARK = "Podpiska-istekla-prodlite-v-Telegram"


def build_inactive_vless_link(remark: str = EXPIRED_SERVER_REMARK) -> str:
    """Non-working VLESS entry so Happ shows an expired notice in the server list."""
    name = encode_vless_fragment(sanitize_remark(remark))
    return f"vless://{EXPIRED_PLACEHOLDER_UUID}@127.0.0.1:1?encryption=none&security=none&type=tcp#{name}"


def build_inactive_subscription_payload(remark: str = EXPIRED_SERVER_REMARK) -> str:
    body = build_inactive_vless_link(remark) + "\n"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def build_xray_subscription_payload(client_uuid: uuid.UUID, remark: str = DEFAULT_REMARK) -> str:
    return build_subscription_payload(client_uuid, remark)
