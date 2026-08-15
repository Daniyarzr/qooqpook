"""Hotfix sub_feed Unicode header bug and restart API only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD")

LOCAL = Path(__file__).resolve().parent.parent / "src/api/routes/sub_feed.py"
REMOTE = "/opt/qooq-vpn/src/api/routes/sub_feed.py"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30, banner_timeout=30)

    sftp = client.open_sftp()
    sftp.put(str(LOCAL), REMOTE)
    sftp.close()
    print("Uploaded sub_feed.py")

    _, stdout, stderr = client.exec_command(
        "cd /opt/qooq-vpn && .venv/bin/python -c "
        "\"from src.api.routes import sub_feed; print('import_ok')\"",
        timeout=60,
    )
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(out)
    if err:
        print(err)
    if "import_ok" not in out:
        print("ABORT")
        client.close()
        return 1

    _, stdout, stderr = client.exec_command(
        "systemctl restart qooq-api && sleep 2 && systemctl is-active qooq-api && "
        "curl -s -o /tmp/sub_out.txt -w '%{http_code}' "
        "'https://keys.qooqvpn.ru/sub/_-o9EsNoNLjwdJ5RdLuvGU5OR9dde18GCFrggpD9PAo' && echo && "
        "head -c 120 /tmp/sub_out.txt && echo",
        timeout=90,
    )
    print(stdout.read().decode("utf-8", errors="replace"))
    print(stderr.read().decode("utf-8", errors="replace"))
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
