"""Deploy promo delete fix — admin only restart."""

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
    "src/services/promo.py",
    "src/admin/app.py",
    "src/admin/templates/promo_codes.html",
]


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def run(client, cmd, timeout=60):
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

    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), remote)
    sftp.close()

    out, err, code = run(
        client,
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.services.promo import PromoCodeService; print('import_ok')\"",
    )
    print(out or err)
    if "import_ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        client,
        "systemctl restart qooq-admin && sleep 2 && systemctl is-active qooq-admin",
    )
    print(out)
    if err:
        print(err)
    client.close()
    print("DONE")
    return 0 if "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
