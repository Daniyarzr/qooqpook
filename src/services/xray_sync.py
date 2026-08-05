"""Sync active client UUIDs to the Xray TLS inbound on the Yandex tunnel node."""

from __future__ import annotations

import copy
import json
import logging
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.core.config import Settings

logger = logging.getLogger(__name__)

QOOQ_EMAIL_PREFIX = "qooq-"


@dataclass(frozen=True)
class XrayClient:
    user_id: int
    device_id: int
    client_uuid: uuid.UUID

    @property
    def email(self) -> str:
        return f"{QOOQ_EMAIL_PREFIX}{self.user_id}-d{self.device_id}"


class XraySyncService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def sync_clients(self, active_clients: list[XrayClient]) -> bool:
        if not self.settings.xray_sync_enabled:
            logger.debug("Xray sync disabled")
            return False

        try:
            import paramiko
        except ImportError:
            logger.error("paramiko is required for Xray sync")
            return False

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        key_path = Path(self.settings.xray_ssh_key_path)
        connect_kwargs: dict = {
            "hostname": self.settings.xray_ssh_host,
            "port": self.settings.xray_ssh_port,
            "username": self.settings.xray_ssh_user,
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
            current = self._read_remote_config(client)
            before = json.dumps(current, sort_keys=True)
            updated = self._merge_clients(copy.deepcopy(current), active_clients)
            after = json.dumps(updated, sort_keys=True)
            if before == after:
                logger.info("Xray config unchanged (%d active clients)", len(active_clients))
                return True

            self._write_remote_config(client, updated)
            self._reload_xray(client)
            logger.info("Xray synced: %d active client UUIDs", len(active_clients))
            return True
        except Exception:
            logger.exception("Xray sync failed")
            return False
        finally:
            client.close()

    def _sudo(self, cmd: str) -> str:
        if self.settings.xray_ssh_use_sudo:
            return f"sudo -n {cmd}"
        return cmd

    def _read_remote_config(self, client) -> dict:
        path = shlex.quote(self.settings.xray_config_path)
        _, stdout, stderr = client.exec_command(self._sudo(f"cat {path}"))
        err = stderr.read().decode()
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(f"Failed to read {path}: {err}")
        return json.loads(stdout.read().decode())

    def _write_remote_config(self, client, config: dict) -> None:
        path = self.settings.xray_config_path
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

    def _reload_xray(self, client) -> None:
        cmd = self._sudo(self.settings.xray_reload_command)
        _, stdout, stderr = client.exec_command(cmd)
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(stderr.read().decode() or "Xray reload failed")

    def _merge_clients(self, config: dict, active_clients: list[XrayClient]) -> dict:
        inbound = self._find_inbound(config)
        if inbound is None:
            raise RuntimeError(
                f"VLESS inbound on port {self.settings.xray_inbound_port} not found"
            )

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

    def _ensure_stats_policy(self, config: dict) -> None:
        policy = config.setdefault("policy", {})
        levels = policy.setdefault("levels", {})
        level0 = levels.setdefault("0", {})
        level0["statsUserUplink"] = True
        level0["statsUserDownlink"] = True
        system = policy.setdefault("system", {})
        system["statsInboundUplink"] = True
        system["statsInboundDownlink"] = True

    def _find_inbound(self, config: dict) -> dict | None:
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") != "vless":
                continue
            if inbound.get("port") == self.settings.xray_inbound_port:
                return inbound
        return None


def sync_active_clients(settings: Settings, active_clients: list[XrayClient]) -> bool:
    return XraySyncService(settings).sync_clients(active_clients)
