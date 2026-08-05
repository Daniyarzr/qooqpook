"""Sync per-user traffic stats from Xray Stats API."""

from __future__ import annotations

import json
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from src.core.config import Settings
from src.core.utils import utcnow
from src.models import Subscription
from src.services.xray_sync import QOOQ_EMAIL_PREFIX

logger = logging.getLogger(__name__)

STAT_PATTERN = re.compile(
    rf"user>>>{re.escape(QOOQ_EMAIL_PREFIX)}(\d+)(?:-d(\d+))?>>>traffic>>>(uplink|downlink)"
)


@dataclass(frozen=True)
class DeviceTraffic:
    user_id: int
    device_id: int | None
    upload: int
    download: int


class TrafficSyncService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_all_traffic(self) -> list[DeviceTraffic]:
        if not self.settings.xray_stats_enabled:
            return []

        raw_stats = self._query_remote_stats()
        keyed: dict[tuple[int, int | None], DeviceTraffic] = {}
        for name, value in raw_stats.items():
            match = STAT_PATTERN.match(name)
            if not match:
                continue
            user_id = int(match.group(1))
            device_id = int(match.group(2)) if match.group(2) else None
            direction = match.group(3)
            key = (user_id, device_id)
            entry = keyed.get(key, DeviceTraffic(user_id=user_id, device_id=device_id, upload=0, download=0))
            if direction == "uplink":
                entry = DeviceTraffic(
                    user_id=user_id, device_id=device_id, upload=value, download=entry.download
                )
            else:
                entry = DeviceTraffic(
                    user_id=user_id, device_id=device_id, upload=entry.upload, download=value
                )
            keyed[key] = entry
        return list(keyed.values())

    def apply_traffic_to_device(
        self,
        device,
        traffic: DeviceTraffic,
    ) -> bool:
        upload_delta = self._calc_delta(traffic.upload, device.traffic_baseline_upload)
        download_delta = self._calc_delta(traffic.download, device.traffic_baseline_download)

        device.bytes_upload += upload_delta
        device.bytes_download += download_delta
        device.traffic_baseline_upload = traffic.upload
        device.traffic_baseline_download = traffic.download
        return upload_delta > 0 or download_delta > 0

    def apply_traffic_to_subscription(
        self,
        subscription: Subscription,
        traffic_list: list[DeviceTraffic],
        devices: list,
    ) -> bool:
        if not devices:
            return False

        updated = False
        legacy_traffic = next(
            (
                item
                for item in traffic_list
                if item.device_id is None and item.user_id == subscription.user_id
            ),
            None,
        )

        for device in devices:
            traffic = next(
                (item for item in traffic_list if item.device_id == device.id),
                None,
            )
            if not traffic and legacy_traffic and len(devices) == 1:
                traffic = legacy_traffic
            if traffic and self.apply_traffic_to_device(device, traffic):
                updated = True

        subscription.bytes_upload = sum(device.bytes_upload for device in devices)
        subscription.bytes_download = sum(device.bytes_download for device in devices)
        subscription.traffic_baseline_upload = sum(
            device.traffic_baseline_upload for device in devices
        )
        subscription.traffic_baseline_download = sum(
            device.traffic_baseline_download for device in devices
        )
        if updated:
            subscription.last_traffic_sync_at = utcnow()
        return updated

    @staticmethod
    def _calc_delta(current_raw: int, baseline: int) -> int:
        if current_raw >= baseline:
            return current_raw - baseline
        return current_raw

    def _query_remote_stats(self) -> dict[str, int]:
        try:
            import paramiko
        except ImportError:
            logger.error("paramiko is required for traffic sync")
            return {}

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
        if not key_path.exists():
            logger.error("Xray SSH key not found: %s", key_path)
            return {}
        connect_kwargs["key_filename"] = str(key_path)

        server = shlex.quote(self.settings.xray_stats_api)
        pattern = shlex.quote(f"user>>>{QOOQ_EMAIL_PREFIX}")
        cmd = f"{self.settings.xray_bin_path} api statsquery --server={server} --pattern={pattern}"

        if self.settings.xray_ssh_use_sudo:
            cmd = f"sudo -n {cmd}"

        try:
            client.connect(**connect_kwargs)
            _, stdout, stderr = client.exec_command(cmd, timeout=30)
            if stdout.channel.recv_exit_status() != 0:
                logger.warning("Traffic stats query failed: %s", stderr.read().decode())
                return {}
            payload = json.loads(stdout.read().decode() or "{}")
        except Exception:
            logger.exception("Traffic stats query failed")
            return {}
        finally:
            client.close()

        stats: dict[str, int] = {}
        for item in payload.get("stat", []):
            name = item.get("name")
            if name:
                stats[name] = int(item.get("value", 0))
        return stats


def get_traffic_limit_gb(subscription: Subscription) -> int | None:
    if subscription.plan and subscription.plan.traffic_limit_gb:
        return subscription.plan.traffic_limit_gb
    return None


def get_traffic_total_bytes(subscription: Subscription) -> int:
    return subscription.bytes_upload + subscription.bytes_download
