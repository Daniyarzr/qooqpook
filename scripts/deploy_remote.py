"""Deploy QooQ VPN to remote server via SSH."""

import os
import secrets
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
REMOTE_DIR = "/opt/qooq-vpn"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {".venv", "__pycache__", ".git", ".ruff_cache", ".pytest_cache", "node_modules"}
EXCLUDE_FILES = {".env"}


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    print(f"\n>>> {cmd[:120]}...")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out[-3000:] if len(out) > 3000 else out)
    if err and code != 0:
        print("STDERR:", err[-2000:])
    return code, out, err


def upload_project(sftp: paramiko.SFTPClient) -> None:
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tar_path = tmp.name

    with tarfile.open(tar_path, "w:gz") as tar:
        for item in PROJECT_ROOT.rglob("*"):
            rel = item.relative_to(PROJECT_ROOT)
            parts = rel.parts
            if parts and parts[0] in EXCLUDE_DIRS:
                continue
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            if item.name in EXCLUDE_FILES:
                continue
            tar.add(item, arcname=str(rel))

    remote_tar = "/tmp/qooq-vpn.tar.gz"
    sftp.put(tar_path, remote_tar)
    os.unlink(tar_path)
    print(f"Uploaded archive to {remote_tar}")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    # Inspect server
    run(client, "uname -a && free -h && ss -tlnp | head -15")
    run(client, "ps aux | grep xray | grep -v grep || true")
    run(client, "docker ps -a 2>/dev/null || true")

    admin_secret = secrets.token_hex(32)
    db_password = secrets.token_urlsafe(16)

    env_content = f"""DATABASE_URL=postgresql+asyncpg://qooq:{db_password}@127.0.0.1:5432/qooq_vpn
DATABASE_URL_SYNC=postgresql://qooq:{db_password}@127.0.0.1:5432/qooq_vpn
REDIS_URL=redis://127.0.0.1:6379/0
BOT_TOKEN=CHANGE_ME
BOT_USERNAME=CHANGE_ME
WEBAPP_URL=http://{HOST}/miniapp
HUB_DOMAIN={HOST}
API_BASE_URL=http://{HOST}
ADMIN_SECRET_KEY={admin_secret}
ADMIN_USERNAME=admin
ADMIN_PASSWORD=QooqAdmin2026!
ADMIN_TELEGRAM_IDS=
DEFAULT_SUBSCRIPTION_DAYS=30
REFERRAL_BONUS_PERCENT=10
REFERRAL_BONUS_DAYS=3
TRIAL_DAYS=3
DEBUG=false
ENVIRONMENT=production
"""

    install_script = f"""#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "=== Installing system packages ==="
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv postgresql redis-server nginx

echo "=== Setting up PostgreSQL ==="
systemctl enable postgresql redis-server nginx
systemctl start postgresql redis-server

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='qooq'" | grep -q 1 || \\
  sudo -u postgres psql -c "CREATE USER qooq WITH PASSWORD '{db_password}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='qooq_vpn'" | grep -q 1 || \\
  sudo -u postgres psql -c "CREATE DATABASE qooq_vpn OWNER qooq;"

echo "=== Deploying app ==="
mkdir -p {REMOTE_DIR}
rm -rf {REMOTE_DIR}/*
tar -xzf /tmp/qooq-vpn.tar.gz -C {REMOTE_DIR}

cd {REMOTE_DIR}
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e . -q

cat > .env << 'ENVEOF'
{env_content}ENVEOF
chmod 600 .env

echo "=== Running migrations ==="
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py

echo "=== Creating systemd services ==="
cat > /etc/systemd/system/qooq-api.service << 'EOF'
[Unit]
Description=QooQ VPN API
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_DIR}
EnvironmentFile={REMOTE_DIR}/.env
ExecStart={REMOTE_DIR}/.venv/bin/uvicorn run_api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/qooq-admin.service << 'EOF'
[Unit]
Description=QooQ VPN Admin Panel
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_DIR}
EnvironmentFile={REMOTE_DIR}/.env
ExecStart={REMOTE_DIR}/.venv/bin/uvicorn run_admin:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/qooq-bot.service << 'EOF'
[Unit]
Description=QooQ VPN Telegram Bot
After=network.target postgresql.service qooq-api.service

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_DIR}
EnvironmentFile={REMOTE_DIR}/.env
ExecStart={REMOTE_DIR}/.venv/bin/python run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/sites-available/qooq-vpn << 'EOF'
server {{
    listen 80;
    server_name {HOST};

    client_max_body_size 10M;

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}

server {{
    listen 8080;
    server_name {HOST};

    location / {{
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
EOF

ln -sf /etc/nginx/sites-available/qooq-vpn /etc/nginx/sites-enabled/qooq-vpn
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

systemctl daemon-reload
systemctl enable qooq-api qooq-admin
systemctl restart qooq-api qooq-admin

# Bot starts only when BOT_TOKEN is set
if grep -q '^BOT_TOKEN=CHANGE_ME' .env; then
  systemctl disable qooq-bot 2>/dev/null || true
  systemctl stop qooq-bot 2>/dev/null || true
  echo "BOT: skipped (set BOT_TOKEN in .env)"
else
  systemctl enable qooq-bot
  systemctl restart qooq-bot
fi

echo "=== DEPLOY DONE ==="
curl -s http://127.0.0.1:8000/health || true
"""

    sftp = client.open_sftp()
    upload_project(sftp)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, newline="\n") as f:
        f.write(install_script)
        local_script = f.name

    sftp.put(local_script, "/tmp/qooq-install.sh")
    os.unlink(local_script)
    sftp.chmod("/tmp/qooq-install.sh", stat.S_IRWXU)
    sftp.close()

    code, out, err = run(client, "bash /tmp/qooq-install.sh", timeout=900)
    client.close()

    if code != 0:
        print(f"Deploy failed with code {code}")
        return code

    print("\n" + "=" * 50)
    print("DEPLOY SUCCESS")
    print(f"API:   http://{HOST}/health")
    print(f"Hub:   http://{HOST}/hub/sub/{{token}}/page")
    print(f"Admin: http://{HOST}:8080/login")
    print("Admin login: admin / QooqAdmin2026!")
    print("Set BOT_TOKEN and BOT_USERNAME in /opt/qooq-vpn/.env")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
