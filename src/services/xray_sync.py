"""Sync active client UUIDs to Xray inbounds (Yandex TLS entry + panel direct)."""

from __future__ import annotations

import copy
import json
import logging
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.core.config import Settings
from src.services.vpn_config import (
    FINLAND_CONFIG_NAME,
    FINLAND_NAME_ALIASES,
    LTE_TUNNEL_CONFIG_NAME,
    LTE_TUNNEL_NAME_ALIASES,
    PANEL_TUNNEL_HOST,
    PANEL_TUNNEL_PORT,
    VPN_HOST,
)

logger = logging.getLogger(__name__)

QOOQ_EMAIL_PREFIX = "qooq-"


@dataclass(frozen=True)
class XrayClient:
    user_id: int
    credential_id: int
    client_uuid: uuid.UUID
    email_override: str | None = None

    @property
    def email(self) -> str:
        if self.email_override:
            return self.email_override
        return f"{QOOQ_EMAIL_PREFIX}{self.user_id}-c{self.credential_id}"


class XraySyncService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def sync_clients(self, active_clients: list[XrayClient]) -> bool:
        if not self.settings.xray_sync_enabled:
            logger.debug("Xray sync disabled")
            return False
        return self._sync_remote(
            active_clients,
            ssh_host=self.settings.xray_ssh_host,
            ssh_port=self.settings.xray_ssh_port,
            ssh_user=self.settings.xray_ssh_user,
            config_path=self.settings.xray_config_path,
            inbound_port=self.settings.xray_inbound_port,
            reload_command=self.settings.xray_reload_command,
            label="Yandex",
        )

    def sync_panel_clients(self, active_clients: list[XrayClient]) -> bool:
        if not self.settings.xray_sync_enabled:
            logger.debug("Panel Xray sync disabled")
            return False
        return self._sync_local(
            active_clients,
            config_path=self.settings.panel_xray_config_path,
            inbound_port=self.settings.panel_xray_inbound_port,
            reload_command=self.settings.panel_xray_reload_command,
            label="Panel",
        )

    def _sync_local(
        self,
        active_clients: list[XrayClient],
        *,
        config_path: str,
        inbound_port: int,
        reload_command: str,
        label: str,
    ) -> bool:
        path = Path(config_path)
        if not path.exists():
            logger.error("%s Xray config not found: %s", label, path)
            return False
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            before = json.dumps(current, sort_keys=True)
            updated = self._merge_clients(
                copy.deepcopy(current),
                active_clients,
                inbound_port=inbound_port,
            )
            after = json.dumps(updated, sort_keys=True)
            if before == after:
                logger.info("%s Xray config unchanged (%d active clients)", label, len(active_clients))
                return True

            tmp_path = path.with_suffix(f".{uuid.uuid4().hex}.json")
            tmp_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)
            path.chmod(0o644)
            self._reload_local(reload_command)
            logger.info("%s Xray synced: %d active client UUIDs", label, len(active_clients))
            return True
        except Exception:
            logger.exception("%s Xray sync failed", label)
            return False

    def _reload_local(self, reload_command: str) -> None:
        import subprocess

        result = subprocess.run(
            reload_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "Xray reload failed")

    def _sync_remote(
        self,
        active_clients: list[XrayClient],
        *,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        config_path: str,
        inbound_port: int,
        reload_command: str,
        label: str,
    ) -> bool:
        try:
            import paramiko
        except ImportError:
            logger.error("paramiko is required for Xray sync")
            return False

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        key_path = Path(self.settings.xray_ssh_key_path)
        connect_kwargs: dict = {
            "hostname": ssh_host,
            "port": ssh_port,
            "username": ssh_user,
            "timeout": 20,
            "look_for_keys": False,
            "allow_agent": False,
        }
        if key_path.exists():
            connect_kwargs["key_filename"] = str(key_path)
        else:
            logger.error("Xray SSH key not found: %s", key_path)
            return False

        try:
            client.connect(**connect_kwargs)
            current = self._read_remote_config(client, config_path)
            before = json.dumps(current, sort_keys=True)
            updated = self._merge_clients(
                copy.deepcopy(current),
                active_clients,
                inbound_port=inbound_port,
            )
            after = json.dumps(updated, sort_keys=True)
            if before == after:
                logger.info("%s Xray config unchanged (%d active clients)", label, len(active_clients))
                return True

            self._write_remote_config(client, updated, config_path)
            self._reload_xray(client, reload_command)
            logger.info("%s Xray synced: %d active client UUIDs", label, len(active_clients))
            return True
        except Exception:
            logger.exception("%s Xray sync failed", label)
            return False
        finally:
            client.close()

    def _sudo(self, cmd: str) -> str:
        if self.settings.xray_ssh_use_sudo:
            return f"sudo -n {cmd}"
        return cmd

    def _read_remote_config(self, client, config_path: str) -> dict:
        path = shlex.quote(config_path)
        _, stdout, stderr = client.exec_command(self._sudo(f"cat {path}"))
        err = stderr.read().decode()
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(f"Failed to read {path}: {err}")
        return json.loads(stdout.read().decode())

    def _write_remote_config(self, client, config: dict, config_path: str) -> None:
        path = config_path
        payload = json.dumps(config, ensure_ascii=False, indent=2)
        tmp_path = f"/tmp/xray-config-{uuid.uuid4().hex}.json"
        quoted_tmp = shlex.quote(tmp_path)
        quoted_path = shlex.quote(path)

        sftp = client.open_sftp()
        try:
            with sftp.open(tmp_path, "w") as remote_file:
                remote_file.write(payload)
        finally:
            sftp.close()

        install_cmd = self._sudo(f"mv {quoted_tmp} {quoted_path} && chmod 644 {quoted_path}")
        _, stdout, stderr = client.exec_command(install_cmd)
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(stderr.read().decode() or "Failed to install Xray config")

    def _reload_xray(self, client, reload_command: str) -> None:
        cmd = self._sudo(reload_command)
        _, stdout, stderr = client.exec_command(cmd)
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(stderr.read().decode() or "Xray reload failed")

    def _merge_clients(
        self,
        config: dict,
        active_clients: list[XrayClient],
        *,
        inbound_port: int,
    ) -> dict:
        targets = self._find_sync_inbounds(config, inbound_port)
        if not targets:
            raise RuntimeError(f"VLESS inbound on port {inbound_port} not found")

        for inbound in targets:
            settings = inbound.setdefault("settings", {})
            existing = settings.get("clients", [])
            preserved = [
                client
                for client in existing
                if not str(client.get("email", "")).startswith(QOOQ_EMAIL_PREFIX)
            ]

            uses_reality = (
                inbound.get("streamSettings", {}).get("security") == "reality"
            )
            managed = []
            for item in active_clients:
                entry = {
                    "id": str(item.client_uuid),
                    "email": item.email,
                    "level": 0,
                }
                if uses_reality:
                    entry["flow"] = "xtls-rprx-vision"
                managed.append(entry)

            settings["clients"] = preserved + managed
            inbound["settings"] = settings

        self._ensure_stats_policy(config)
        return config

    def _find_sync_inbounds(self, config: dict, inbound_port: int) -> list[dict]:
        """VLESS TCP (white2) + lte-xhttp backends после nginx SNI mux."""
        found: list[dict] = []
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") != "vless":
                continue
            port = inbound.get("port")
            tag = inbound.get("tag")
            network = (inbound.get("streamSettings") or {}).get("network") or "tcp"
            if tag in {"lte-xhttp", "vless-tcp", "vless-reality"}:
                found.append(inbound)
            elif port in {inbound_port, 8443, 10443, 18443, 11443} or network == "xhttp":
                found.append(inbound)
        # unique by id(object)
        uniq: list[dict] = []
        seen: set[int] = set()
        for ib in found:
            i = id(ib)
            if i not in seen:
                seen.add(i)
                uniq.append(ib)
        return uniq

    def _find_inbound(self, config: dict, inbound_port: int) -> dict | None:
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") != "vless":
                continue
            if inbound.get("port") == inbound_port:
                return inbound
        return None

    def _ensure_stats_policy(self, config: dict) -> None:
        policy = config.setdefault("policy", {})
        levels = policy.setdefault("levels", {})
        level0 = levels.setdefault("0", {})
        level0["statsUserUplink"] = True
        level0["statsUserDownlink"] = True
        system = policy.setdefault("system", {})
        system["statsInboundUplink"] = True
        system["statsInboundDownlink"] = True


def _config_points_to_panel(config) -> bool:
    """True if JSON outbound goes direct to panel :10086 (Finland QooQ)."""
    if not config or not config.config_template:
        return False
    try:
        data = json.loads(config.config_template)
    except (json.JSONDecodeError, TypeError):
        return False
    for outbound in data.get("outbounds") or []:
        if outbound.get("protocol") != "vless":
            continue
        try:
            vnext = outbound["settings"]["vnext"][0]
            address = str(vnext.get("address") or "")
            port = int(vnext.get("port") or 0)
            if address == PANEL_TUNNEL_HOST and port == PANEL_TUNNEL_PORT:
                return True
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return False


def _config_points_to_yandex_entry(config) -> bool:
    """True if JSON outbound goes to Yandex entry host / LTE SNI."""
    if not config or not config.config_template:
        return False
    try:
        data = json.loads(config.config_template)
    except (json.JSONDecodeError, TypeError):
        return False
    for outbound in data.get("outbounds") or []:
        if outbound.get("protocol") != "vless":
            continue
        try:
            vnext = outbound["settings"]["vnext"][0]
            address = str(vnext.get("address") or "")
            if address in {VPN_HOST, "white.qooqvpn.ru", "white2.qooqvpn.ru"}:
                return True
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return False


def _split_clients_by_config(
    credentials,
) -> tuple[list[XrayClient], list[XrayClient]]:
    tunnel_clients: list[XrayClient] = []
    panel_clients: list[XrayClient] = []
    for credential in credentials:
        if not credential.subscription:
            continue
        client = XrayClient(
            user_id=credential.subscription.user_id,
            credential_id=credential.id,
            client_uuid=credential.client_uuid,
        )
        config = credential.vpn_config
        config_name = config.name if config else ""
        if (
            config_name in FINLAND_NAME_ALIASES
            or _config_points_to_panel(config)
        ):
            panel_clients.append(client)
        elif (
            config_name in LTE_TUNNEL_NAME_ALIASES
            or _config_points_to_yandex_entry(config)
            or not config_name
        ):
            tunnel_clients.append(client)
        else:
            # Чужие JSON (США/Германия/…) на наш Xray не кладём
            continue
    return tunnel_clients, panel_clients


def sync_active_clients(settings: Settings, active_clients: list[XrayClient]) -> bool:
    return XraySyncService(settings).sync_clients(active_clients)


def sync_all_active_clients(settings: Settings, credentials) -> bool:
    tunnel_clients, panel_clients = _split_clients_by_config(credentials)
    service = XraySyncService(settings)
    yandex_ok = service.sync_clients(tunnel_clients)
    panel_ok = service.sync_panel_clients(panel_clients)
    return yandex_ok and panel_ok
