"""Debug subscription feed on production."""
import os
import sys

import paramiko

HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "Rider_123")


def run(client, cmd: str) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return out + err


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    token = run(
        client,
        "sudo -u postgres psql -d qooq_vpn -t -A -c "
        "\"SELECT subscription_token FROM subscriptions WHERE expires_at > now() "
        "ORDER BY id DESC LIMIT 1;\"",
    ).strip()
    print("TOKEN:", token)

    print(run(client, f"curl -sk -D /tmp/hdrs.txt -o /tmp/sub.b64 'https://keys.qooqvpn.ru/sub/{token}'"))
    print("--- headers ---")
    print(run(client, "cat /tmp/hdrs.txt"))
    print("--- body preview ---")
    print(run(client, "head -c 200 /tmp/sub.b64; echo"))
    print("--- decode preview ---")
    print(run(client, "base64 -d /tmp/sub.b64 2>/dev/null | head -c 300; echo"))
    print("--- recent api errors ---")
    print(run(client, "journalctl -u qooq-api -n 15 --no-pager | grep -E '500|Unicode|sub/' || true"))
    print("--- prod sub_feed snippet ---")
    print(run(client, "grep -n 'sub-info-text\\|_encode_happ\\|update-always' /opt/qooq-vpn/src/api/routes/sub_feed.py | head -20"))

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
