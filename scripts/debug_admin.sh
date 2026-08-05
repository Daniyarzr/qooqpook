#!/bin/bash
curl -s -o /dev/null -w "8001_login:%{http_code}\n" http://127.0.0.1:8001/login
curl -sk -o /dev/null -w "panel_login:%{http_code}\n" https://keys.qooqvpn.ru/panel/login
curl -sk -o /dev/null -w "8080_login:%{http_code}\n" http://148.135.184.188:8080/login
