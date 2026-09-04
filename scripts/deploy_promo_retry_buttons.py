import os
import sys
import time
from pathlib import Path

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE = "/opt/qooq-vpn"
PROJECT = Path(__file__).resolve().parent.parent
FILES = [
    "src/bot/keyboards/inline.py",
    "src/bot/handlers/subscription.py",
]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
sftp = client.open_sftp()
for rel in FILES:
    sftp.put(str(PROJECT / rel), f"{REMOTE}/{rel}")
    print("uploaded", rel)
sftp.close()


def run(cmd: str, t: int = 60) -> None:
    _, o, e = client.exec_command(cmd, timeout=t)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err[-1500:])


run(
    f"cd {REMOTE} && .venv/bin/python -c "
    "'from src.bot.keyboards.inline import promo_error_keyboard; "
    "print(promo_error_keyboard(9).inline_keyboard[0][0].text)'"
)
run("systemctl restart qooq-bot")
time.sleep(4)
run("systemctl is-active qooq-bot")
run("journalctl -u qooq-bot -n 8 --no-pager")
client.close()
print("DONE")
