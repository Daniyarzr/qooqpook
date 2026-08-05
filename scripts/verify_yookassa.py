import paramiko
import os

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    "148.135.184.188",
    username="root",
    password=os.environ["DEPLOY_PASSWORD"],
    timeout=15,
)

commands = [
    "curl -s http://127.0.0.1:8000/health",
    'curl -s -o /dev/null -w "webhook:%{http_code}" -X POST http://127.0.0.1:8000/api/v1/payments/yookassa/webhook -H "Content-Type: application/json" -d "{}"',
    'cd /opt/qooq-vpn && .venv/bin/python -c "from src.bot.app import create_bot; create_bot(); print(\'bot ok\')"',
    "journalctl -u qooq-bot -n 8 --no-pager",
]

for cmd in commands:
    print(">>>", cmd)
    _, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        print(out)
    if err:
        print("ERR:", err)

client.close()
