#!/bin/bash
set -ex

cat > /etc/nginx/sites-available/qooq-vpn << 'EOF'
server {
    listen 80;
    server_name keys.qooqvpn.ru;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name keys.qooqvpn.ru;

    ssl_certificate /etc/nginx/ssl/keys.qooqvpn.ru/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/keys.qooqvpn.ru/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /panel/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/qooq-vpn /etc/nginx/sites-enabled/qooq-vpn
nginx -t && systemctl reload nginx
curl -sk -o /dev/null -w "panel:%{http_code}\n" https://keys.qooqvpn.ru/panel/login
curl -sk https://keys.qooqvpn.ru/health
