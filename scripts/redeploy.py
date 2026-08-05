"""Quick redeploy updated code to server."""

import os
import stat
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
if not PASSWORD:
    raise SystemExit("Set DEPLOY_PASSWORD environment variable")
PROJECT = Path(__file__).resolve().parent.parent
EXCLUDE = {".venv", "__pycache__", ".git", ".ruff_cache"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tar_path = tmp.name

    with tarfile.open(tar_path, "w:gz") as tar:
        for item in PROJECT.rglob("*"):
            rel = item.relative_to(PROJECT)
            if any(p in EXCLUDE for p in rel.parts) or item.name == ".env":
                continue
            tar.add(item, arcname=str(rel))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    sftp = client.open_sftp()
    sftp.put(tar_path, "/tmp/qooq-vpn.tar.gz")
    os.unlink(tar_path)

    update_script = """#!/bin/bash
set -ex
cd /opt/qooq-vpn
tar -xzf /tmp/qooq-vpn.tar.gz
.venv/bin/pip install -e . -q
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py
systemctl daemon-reload
systemctl restart qooq-api qooq-admin qooq-bot 2>/dev/null || systemctl restart qooq-api qooq-admin
# Xray UUID sync every 5 minutes (when SSH key configured)
grep -q sync_xray_users.py /etc/cron.d/qooq-vpn 2>/dev/null || cat > /etc/cron.d/qooq-vpn <<'CRON'
*/5 * * * * root cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py >> /var/log/qooq-xray-sync.log 2>&1
*/5 * * * * root cd /opt/qooq-vpn && .venv/bin/python scripts/sync_traffic.py >> /var/log/qooq-traffic-sync.log 2>&1
CRON
"""

    with sftp.open("/tmp/update.sh", "w") as f:
        f.write(update_script.replace("\r\n", "\n"))
    sftp.chmod("/tmp/update.sh", stat.S_IRWXU)

    # Ensure nginx 8080 config exists
    finish = (PROJECT / "scripts" / "finish_install.sh").read_bytes().replace(b"\r\n", b"\n")
    with sftp.open("/tmp/finish_install.sh", "w") as f:
        f.write(finish.decode("utf-8"))
    sftp.chmod("/tmp/finish_install.sh", stat.S_IRWXU)
    sftp.close()

    _, stdout, _ = client.exec_command("bash /tmp/update.sh 2>&1", timeout=600)
    print(stdout.read().decode("utf-8", errors="replace"))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
