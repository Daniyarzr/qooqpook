"""Deploy: JSON configs no longer force-bind to Yandex."""
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
    "src/services/vpn_config.py",
    "src/services/vpn_config_store.py",
    "src/services/__init__.py",
    "src/admin/services.py",
    "src/admin/app.py",
    "src/admin/templates/configs.html",
    "src/admin/templates/config_detail.html",
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

    def run(cmd: str, timeout: int = 120) -> None:
        print("$", cmd)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out.strip():
            print(out)
        if err.strip():
            print(err)

    run(
        f"cd {REMOTE} && .venv/bin/python -c \""
        "from src.services.vpn_config import build_vless_link_for_server, extract_vless_endpoint; "
        "from src.admin.services import AdminService; "
        "print('import ok')\""
    )
    run("systemctl restart qooq-admin qooq-api")
    run("systemctl is-active qooq-admin qooq-api")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
