"""Enable Xray stats and traffic sync cron on production."""

import os
import re
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")

ENV_UPDATES = {
    "XRAY_STATS_ENABLED": "true",
    "XRAY_STATS_API": "127.0.0.1:10085",
    "XRAY_BIN_PATH": "xray",
}

CRON_CONTENT = """*/5 * * * * root cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py >> /var/log/qooq-xray-sync.log 2>&1
*/5 * * * * root cd /opt/qooq-vpn && .venv/bin/python scripts/sync_traffic.py >> /var/log/qooq-traffic-sync.log 2>&1
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    _, stdout, _ = client.exec_command("cat /opt/qooq-vpn/.env")
    env = stdout.read().decode("utf-8", errors="replace")
    for key, value in ENV_UPDATES.items():
        line = f"{key}={value}"
        if re.search(rf"^{key}=.*$", env, flags=re.M):
            env = re.sub(rf"^{key}=.*$", line, env, flags=re.M)
        else:
            env += line + "\n"

    sftp = client.open_sftp()
    with sftp.open("/opt/qooq-vpn/.env", "w") as f:
        f.write(env)
    with sftp.open("/etc/cron.d/qooq-vpn", "w") as f:
        f.write(CRON_CONTENT)
    sftp.close()

    for cmd in [
        "systemctl restart qooq-api qooq-admin",
        "cd /opt/qooq-vpn && .venv/bin/python -c \"from src.core.config import get_settings; s=get_settings(); print(s.xray_stats_enabled)\"",
    ]:
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        if out:
            print(out)
        if err:
            print("ERR:", err)

    client.close()
    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
