"""Configure and start Telegram bot on server."""

import os
import re
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD")
TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

BOT_SERVICE = """[Unit]
Description=QooQ VPN Telegram Bot
After=network.target postgresql.service qooq-api.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/qooq-vpn
EnvironmentFile=/opt/qooq-vpn/.env
ExecStart=/opt/qooq-vpn/.venv/bin/python run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not TOKEN or not BOT_USERNAME:
        print("Set BOT_TOKEN and BOT_USERNAME env vars")
        raise SystemExit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    _, stdout, _ = client.exec_command("cat /opt/qooq-vpn/.env")
    env = stdout.read().decode()
    env = re.sub(r"^BOT_TOKEN=.*$", f"BOT_TOKEN={TOKEN}", env, flags=re.M)
    env = re.sub(r"^BOT_USERNAME=.*$", f"BOT_USERNAME={BOT_USERNAME}", env, flags=re.M)

    sftp = client.open_sftp()
    with sftp.open("/opt/qooq-vpn/.env", "w") as f:
        f.write(env)
    with sftp.open("/etc/systemd/system/qooq-bot.service", "w") as f:
        f.write(BOT_SERVICE)
    sftp.close()

    commands = [
        "cd /opt/qooq-vpn && .venv/bin/python -c 'from src.bot.app import create_bot; create_bot(); print(\"ok\")'",
        "systemctl daemon-reload",
        "systemctl enable qooq-bot",
        "systemctl restart qooq-bot",
        "sleep 4",
        "systemctl is-active qooq-bot",
        "journalctl -u qooq-bot -n 20 --no-pager",
    ]

    for cmd in commands:
        print(f">>> {cmd}")
        _, stdout, stderr = client.exec_command(cmd, timeout=60)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            print(out)
        if err:
            print("ERR:", err)

    client.close()


if __name__ == "__main__":
    main()
