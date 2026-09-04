"""Deploy expired Telegram-only subscription feed."""

from __future__ import annotations

import os
import sys
import time
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
    "src/services/xray_sync.py",
    "src/api/routes/sub_feed.py",
]


def ensure_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        local = PROJECT / rel
        remote = f"{REMOTE}/{rel}"
        ensure_dir(sftp, str(Path(remote).parent).replace("\\", "/"))
        sftp.put(str(local), remote)
        print("uploaded", rel)
    sftp.close()

    def run(cmd: str, t: int = 120) -> int:
        _, o, e = client.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", errors="replace")
        err = e.read().decode("utf-8", errors="replace")
        code = o.channel.recv_exit_status()
        text = (out + (("\n" + err) if err.strip() else "")).strip()
        if text:
            print(text)
        return code

    print("=== import check ===")
    code = run(
        f"cd {REMOTE} && .venv/bin/python -c "
        "'from src.services.vpn_config import EXPIRED_ANNOUNCE_UUID, build_happ_telegram_only_routing_link; "
        "from src.api.routes.sub_feed import _build_inactive_response; "
        "print(EXPIRED_ANNOUNCE_UUID); "
        "print(build_happ_telegram_only_routing_link()[:32])'"
    )
    if code != 0:
        client.close()
        return code

    print("=== restart api ===")
    run("systemctl restart qooq-api")
    time.sleep(4)
    run("systemctl is-active qooq-api")

    print("=== sync xray (add announce uuid) ===")
    run(f"cd {REMOTE} && .venv/bin/python scripts/sync_xray_users.py", t=180)

    print("=== verify announce email on panel ===")
    run(
        "python3 - <<'PY'\n"
        "import json\n"
        "cfg=json.load(open('/usr/local/etc/xray/config.json'))\n"
        "found=[]\n"
        "for ib in cfg.get('inbounds',[]):\n"
        "  for c in (ib.get('settings') or {}).get('clients') or []:\n"
        "    if 'announce' in str(c.get('email','')) or str(c.get('id','')).startswith('c0ffee00'):\n"
        "      found.append((ib.get('tag'), c.get('email'), c.get('id')))\n"
        "print(found or 'NOT FOUND')\n"
        "PY"
    )

    run("journalctl -u qooq-api -n 12 --no-pager")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
