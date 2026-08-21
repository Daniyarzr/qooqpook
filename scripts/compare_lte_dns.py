"""Compare DNS of working LTE hosts vs our entry."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ["DEPLOY_PASSWORD"]
HOSTS = [
    "white.qooqvpn.ru",
    "white2.qooqvpn.ru",
    "gateway.kitsura.fun",
    "yc-swe-002.nyako.app",
    "51.250.32.123",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.135.184.188", username="root", password=PASSWORD, timeout=30)
    script = "\n".join(
        f'echo "== {h} =="; dig +short {h} A || true; '
        f'getent hosts {h} || true; '
        f'curl -sS -m 6 https://ipinfo.io/{h} 2>/dev/null | head -c 400; echo'
        for h in HOSTS
        if not h[0].isdigit()
    )
    script += """
echo '== panel :443 =';
ss -lntp | grep -E ':443|:10086' || true
"""
    # resolve kitsura IP then ipinfo
    script += """
for h in gateway.kitsura.fun yc-swe-002.nyako.app white2.qooqvpn.ru; do
  ip=$(dig +short "$h" A | head -1)
  echo "HOST $h -> $ip"
  if [ -n "$ip" ]; then curl -sS -m 6 "https://ipinfo.io/$ip"; echo; fi
done
"""
    _, o, e = client.exec_command(script, timeout=90)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err[-1500:])
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
