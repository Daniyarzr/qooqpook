#!/bin/bash
echo NGINX:
nginx -t 2>&1
ss -tlnp | grep ':80 '
echo ---
ls -la /etc/nginx/sites-enabled/
echo ---
cat /etc/nginx/sites-enabled/qooq-acme
echo ---
curl -v http://127.0.0.1/.well-known/acme-challenge/test -H 'Host: keys.qooqvpn.ru' 2>&1 | tail -15
echo ---
host -t A app.qooqvpn.ru admin.qooqvpn.ru 2>&1
journalctl -u qooq-bot -n 5 --no-pager
