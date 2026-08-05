#!/bin/bash
systemctl is-active qooq-api qooq-admin qooq-bot
curl -s http://127.0.0.1:8000/health
echo
curl -sk https://keys.qooqvpn.ru/health
echo
journalctl -u qooq-api -n 8 --no-pager
