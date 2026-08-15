"""Deploy payment notification idempotency fix."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/services/payment.py",
    "src/services/notifications.py",
    "src/repositories/__init__.py",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    sftp.close()

    def run(cmd: str, timeout: int = 90):
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err, stdout.channel.recv_exit_status()

    out, err, code = run(
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.repositories import PaymentOrderRepository; "
        "assert hasattr(PaymentOrderRepository, 'get_by_external_id_for_update'); "
        "print('ok')\""
    )
    print("IMPORT:", out, err)
    if "ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        "systemctl restart qooq-api qooq-bot && sleep 2 && systemctl is-active qooq-api qooq-bot"
    )
    print("RESTART:", out.strip())
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
