"""Deploy expired-sub renew in admin and purchase nudges. Admin restart only."""

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
    "alembic/versions/017_purchase_nudge_sent.py",
    "src/models/__init__.py",
    "src/admin/app.py",
    "src/admin/services.py",
    "src/admin/templates/user_detail.html",
    "src/admin/templates/users.html",
    "src/services/expiry_reminders.py",
    "scripts/notify_subscription_expiry.py",
]


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def run(client, cmd, timeout=120):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)

    out, err, _ = run(client, "systemctl is-active qooq-api qooq-bot qooq-admin")
    print("BEFORE:\n" + out)
    if err.strip():
        print(err)

    out, err, _ = run(client, "rm -f /opt/qooq-vpn/alembic/versions/016_purchase_nudge_sent.py; echo removed_conflict")
    print(out)

    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), remote)
    sftp.close()

    out, err, code = run(
        client,
        f"cd {REMOTE} && .venv/bin/alembic upgrade head",
        timeout=180,
    )
    print(out)
    if err.strip():
        print(err)
    if code != 0:
        print("MIGRATION FAILED")
        client.close()
        return 1

    out, err, _ = run(
        client,
        f"cd {REMOTE} && .venv/bin/python -c "
        "\"from src.models import PartnerLink; "
        "from src.admin.app import create_admin_app; "
        "from src.services.expiry_reminders import PurchaseNudgeService; "
        "print('import_ok')\"",
    )
    print(out or err)
    if "import_ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        client,
        "systemctl restart qooq-admin && sleep 2 && "
        "systemctl is-active qooq-admin qooq-api qooq-bot",
    )
    print(out)
    if err.strip():
        print(err)
    client.close()
    ok = "active" in out and out.count("active") >= 3
    print("DONE" if ok else "CHECK STATUSES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
