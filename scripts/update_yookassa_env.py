"""Update YooKassa credentials on production server."""

import os
import re
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")

UPDATES = {
    "YOOKASSA_SHOP_ID": os.environ.get("YOOKASSA_SHOP_ID", ""),
    "YOOKASSA_SECRET_KEY": os.environ.get("YOOKASSA_SECRET_KEY", ""),
    "DEPOSIT_AMOUNTS": os.environ.get("DEPOSIT_AMOUNTS", "100,300,500,1000,2000"),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")
    if not UPDATES["YOOKASSA_SHOP_ID"] or not UPDATES["YOOKASSA_SECRET_KEY"]:
        raise SystemExit("Set YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    _, stdout, _ = client.exec_command("cat /opt/qooq-vpn/.env")
    env = stdout.read().decode("utf-8", errors="replace")

    for key, value in UPDATES.items():
        pattern = rf"^{key}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, env, flags=re.M):
            env = re.sub(pattern, line, env, flags=re.M)
        else:
            if not env.endswith("\n"):
                env += "\n"
            env += line + "\n"

    match = re.search(r"^BOT_USERNAME=(.*)$", env, flags=re.M)
    if match and match.group(1).strip():
        return_url = f"https://t.me/{match.group(1).strip()}"
        if re.search(r"^YOOKASSA_RETURN_URL=.*$", env, flags=re.M):
            env = re.sub(
                r"^YOOKASSA_RETURN_URL=.*$",
                f"YOOKASSA_RETURN_URL={return_url}",
                env,
                flags=re.M,
            )
        else:
            env += f"YOOKASSA_RETURN_URL={return_url}\n"

    sftp = client.open_sftp()
    with sftp.open("/opt/qooq-vpn/.env", "w") as f:
        f.write(env)
    sftp.close()

    commands = [
        'cd /opt/qooq-vpn && .venv/bin/python -c "from src.core.config import get_settings; s=get_settings(); print(s.yookassa_enabled, s.bot_username)"',
        "systemctl restart qooq-api qooq-bot",
        "sleep 2",
        "systemctl is-active qooq-api qooq-bot",
        "curl -s http://127.0.0.1:8000/health",
    ]
    for cmd in commands:
        print(f">>> {cmd}")
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
