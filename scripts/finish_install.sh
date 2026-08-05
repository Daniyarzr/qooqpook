#!/bin/bash
set -ex
cd /opt/qooq-vpn

echo "=== pip install ==="
.venv/bin/pip install -e . 2>&1 | tail -30

echo "=== alembic ==="
.venv/bin/alembic upgrade head

echo "=== seed ==="
.venv/bin/python scripts/seed.py

echo "=== test ==="
.venv/bin/python -c "from run_api import app; print('api ok')"

echo "=== nginx 8080 ==="
if ! grep -q 'listen 8080' /etc/nginx/sites-available/qooq-vpn 2>/dev/null; then
cat > /etc/nginx/sites-available/qooq-vpn << 'NGINXEOF'
server {
    listen 80;
    server_name 148.135.184.188;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 8080;
    server_name 148.135.184.188;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINXEOF
ln -sf /etc/nginx/sites-available/qooq-vpn /etc/nginx/sites-enabled/qooq-vpn
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
fi

echo "=== systemd ==="
cat > /etc/systemd/system/qooq-api.service << 'EOF'
[Unit]
Description=QooQ VPN API
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/qooq-vpn
EnvironmentFile=/opt/qooq-vpn/.env
ExecStart=/opt/qooq-vpn/.venv/bin/uvicorn run_api:app --host 127.0.0.1 --port 8000
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
WorkingDirectory=/opt/qooq-vpn
EnvironmentFile=/opt/qooq-vpn/.env
ExecStart=/opt/qooq-vpn/.venv/bin/uvicorn run_admin:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable qooq-api qooq-admin
systemctl restart qooq-api qooq-admin
sleep 3

echo "=== status ==="
systemctl is-active qooq-api qooq-admin
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "admin:%{http_code}\n" http://127.0.0.1:8001/login

echo "=== DONE ==="
