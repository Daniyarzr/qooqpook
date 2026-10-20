"""Deploy external subscription import. Restarts admin and API only."""

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
    "alembic/versions/018_imported_subscriptions.py",
    "src/models/__init__.py",
    "src/services/imported_subs.py",
    "src/admin/app.py",
    "src/admin/templates/imported_subs.html",
    "src/api/routes/sub_feed.py",
    "scripts/check_imported_subs.py",
]

NAV_SNIPPET = '            <a href="/imported-subs">🌐 Импорт подписок</a>\n'
CRON_LINE = (
    "*/30 * * * * root cd /opt/qooq-vpn && "
    "/usr/bin/flock -n /tmp/qooq-imported-subs.lock "
    ".venv/bin/python scripts/check_imported_subs.py "
    ">> /var/log/qooq-imported-subs.log 2>&1\n"
)


def ensure_dir(sftp, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def run(client, cmd, timeout=180):
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

    out, _, _ = run(client, "systemctl is-active qooq-api qooq-bot qooq-admin")
    print("BEFORE:\n" + out)

    sftp = client.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        print("Upload", rel)
        sftp.put(str(PROJECT / rel), remote)

    base_path = f"{REMOTE}/src/admin/templates/base.html"
    with sftp.open(base_path, "rb") as fh:
        base = fh.read().decode("utf-8", errors="replace")
    if 'href="/imported-subs"' not in base:
        marker = '            <a href="/configs">'
        if marker not in base:
            print("NAV MARKER MISSING")
            sftp.close()
            client.close()
            return 1
        base = base.replace(marker, NAV_SNIPPET + marker, 1)
        with sftp.open(base_path, "wb") as fh:
            fh.write(base.encode("utf-8"))
        print("Nav link added")
    else:
        print("Nav link already present")

    cron_path = "/etc/cron.d/qooq-vpn"
    with sftp.open(cron_path, "rb") as fh:
        cron = fh.read().decode("utf-8", errors="replace")
    if "check_imported_subs.py" not in cron:
        if not cron.endswith("\n"):
            cron += "\n"
        cron += CRON_LINE
        with sftp.open(cron_path, "wb") as fh:
            fh.write(cron.encode("utf-8"))
        print("Cron line added")
    else:
        print("Cron line already present")
    sftp.close()

    out, err, code = run(client, f"cd {REMOTE} && .venv/bin/alembic upgrade head")
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
        "\"from src.services.imported_subs import parse_subscription_body; "
        "from src.admin.app import create_admin_app; "
        "print('import_ok')\"",
    )
    print(out or err)
    if "import_ok" not in out:
        client.close()
        return 1

    out, err, _ = run(
        client,
        "systemctl restart qooq-admin qooq-api && sleep 3 && "
        "systemctl is-active qooq-admin qooq-api qooq-bot",
    )
    print(out)
    if err.strip():
        print(err)
    client.close()
    ok = out.count("active") >= 3
    print("DONE" if ok else "CHECK STATUSES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
