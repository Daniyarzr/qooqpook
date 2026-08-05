#!/usr/bin/env python3
import json
import urllib.request

domains = [
    "keys.qooqvpn.ru",
    "admin.qooqvpn.ru",
    "app.qooqvpn.ru",
    "admin.keys.qooqvpn.ru",
    "app.keys.qooqvpn.ru",
    "qooqvpn.ru",
]

for d in domains:
    try:
        url = f"https://dns.google/resolve?name={d}&type=A"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
        answers = [a.get("data") for a in data.get("Answer", []) if a.get("type") in (1, 5)]
        status = data.get("Status")
        label = answers if answers else "NO A RECORD"
        print(f"{d:30} -> {label}  (status={status})")
    except Exception as e:
        print(f"{d:30} -> ERROR {e}")

# NS records
print("\nNS for qooqvpn.ru:")
url = "https://dns.google/resolve?name=qooqvpn.ru&type=NS"
with urllib.request.urlopen(url, timeout=10) as r:
    data = json.load(r)
for a in data.get("Answer", []):
    print(" ", a.get("data"))
