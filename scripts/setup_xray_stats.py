"""Safely enable Xray Stats API on Yandex node without breaking VPN."""

import copy
import json
import os
import sys
from datetime import datetime, timezone

import paramiko

PANEL_HOST = "148.135.184.188"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")
SSH_KEY = "/root/.ssh/qooq_xray"
REMOTE_USER = "adminka"
REMOTE_HOST = "51.250.32.123"
CONFIG_PATH = "/usr/local/etc/xray/config.json"
STATS_PORT = 10085


def run(client, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")


def ssh_remote(cmd: str) -> tuple[int, str, str]:
    escaped = cmd.replace("'", "'\\''")
    full = (
        f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15 "
        f"{REMOTE_USER}@{REMOTE_HOST} '{escaped}'"
    )
    return run(client, full, timeout=90)


def merge_stats_api(config: dict) -> tuple[dict, list[str]]:
    changes: list[str] = []
    updated = copy.deepcopy(config)

    if "stats" not in updated:
        updated["stats"] = {}
        changes.append("added stats")

    api = updated.setdefault("api", {})
    if api.get("tag") != "api" or "StatsService" not in api.get("services", []):
        updated["api"] = {"tag": "api", "services": ["StatsService"]}
        changes.append("added api StatsService")

    inbounds = updated.setdefault("inbounds", [])
    if not any(item.get("tag") == "api" for item in inbounds):
        inbounds.append(
            {
                "listen": "127.0.0.1",
                "port": STATS_PORT,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
                "tag": "api",
            }
        )
        changes.append(f"added api inbound on {STATS_PORT}")

    outbounds = updated.setdefault("outbounds", [])
    if not any(item.get("tag") == "api" for item in outbounds):
        outbounds.append({"protocol": "freedom", "tag": "api"})
        changes.append("added api outbound")

    routing = updated.setdefault("routing", {})
    rules = routing.setdefault("rules", [])
    if not any(
        rule.get("inboundTag") == ["api"] and rule.get("outboundTag") == "api"
        for rule in rules
    ):
        rules.insert(0, {"inboundTag": ["api"], "outboundTag": "api", "type": "field"})
        changes.append("added api routing rule")

    policy = updated.setdefault("policy", {})
    levels = policy.setdefault("levels", {})
    level0 = levels.setdefault("0", {})
    if not level0.get("statsUserUplink"):
        level0["statsUserUplink"] = True
        changes.append("enabled statsUserUplink")
    if not level0.get("statsUserDownlink"):
        level0["statsUserDownlink"] = True
        changes.append("enabled statsUserDownlink")

    system = policy.setdefault("system", {})
    if not system.get("statsInboundUplink"):
        system["statsInboundUplink"] = True
        changes.append("enabled statsInboundUplink")
    if not system.get("statsInboundDownlink"):
        system["statsInboundDownlink"] = True
        changes.append("enabled statsInboundDownlink")

    return updated, changes


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    global client
    if not PASSWORD:
        raise SystemExit("Set DEPLOY_PASSWORD")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(PANEL_HOST, username=USER, password=PASSWORD, timeout=15)

    print("=== 1. Read current remote config ===")
    code, out, err = ssh_remote(f"sudo cat {CONFIG_PATH}")
    if code != 0:
        print("FAILED to read config:", err or out)
        return 1

    try:
        current = json.loads(out)
    except json.JSONDecodeError as exc:
        print("Invalid JSON in current config:", exc)
        return 1

    vless_inbound = next(
        (i for i in current.get("inbounds", []) if i.get("protocol") == "vless" and i.get("port") == 443),
        None,
    )
    if not vless_inbound:
        print("ABORT: VLESS inbound on 443 not found — won't touch config")
        return 1

    clients_before = len(vless_inbound.get("settings", {}).get("clients", []))
    print(f"OK: VLESS :443 found, {clients_before} clients")

    print("\n=== 2. Check if stats API already works ===")
    code, out, err = ssh_remote(
        f"sudo xray api statsquery --server=127.0.0.1:{STATS_PORT} --pattern=user 2>&1"
    )
    if code == 0 and "stat" in out:
        print("Stats API already working, no changes needed")
        print(out[:500])
        return 0
    print("Stats API not available yet:", (out or err).strip()[:200])

    print("\n=== 3. Build merged config ===")
    merged, changes = merge_stats_api(current)
    if not changes:
        print("Nothing to merge — unexpected")
        return 1
    print("Planned changes:", ", ".join(changes))

    merged_json = json.dumps(merged, ensure_ascii=False, indent=2)
    if merged_json == json.dumps(current, ensure_ascii=False, indent=2):
        print("Config unchanged after merge — abort")
        return 1

    clients_after = len(
        next(i for i in merged["inbounds"] if i.get("protocol") == "vless")["settings"]["clients"]
    )
    if clients_after != clients_before:
        print(f"ABORT: client count changed {clients_before} -> {clients_after}")
        return 1

    print("\n=== 4. Backup + upload + validate ===")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = f"{CONFIG_PATH}.bak.{ts}"
    ssh_remote(f"sudo cp {CONFIG_PATH} {backup_path}")
    print(f"Backup: {backup_path}")

    # Upload via panel temp file + scp to remote
    local_tmp = f"/tmp/xray-config-{ts}.json"
    sftp = client.open_sftp()
    with sftp.open(local_tmp, "w") as f:
        f.write(merged_json)
    sftp.close()

    remote_tmp = f"/tmp/xray-config-{ts}.json"
    scp_cmd = (
        f"scp -i {SSH_KEY} -o StrictHostKeyChecking=no {local_tmp} "
        f"{REMOTE_USER}@{REMOTE_HOST}:{remote_tmp}"
    )
    code, out, err = run(client, scp_cmd)
    if code != 0:
        print("SCP failed:", err or out)
        return 1

    code, out, err = ssh_remote(f"sudo xray run -test -config {remote_tmp} 2>&1")
    test_output = (out + err).strip()
    print("Config test:", test_output)
    if code != 0 or "failed" in test_output.lower():
        print("ABORT: config test failed, not applying")
        ssh_remote(f"rm -f {remote_tmp}")
        run(client, f"rm -f {local_tmp}")
        return 1

    print("\n=== 5. Apply config + restart xray ===")
    code, out, err = ssh_remote(
        f"sudo cp {remote_tmp} {CONFIG_PATH} && sudo chmod 644 {CONFIG_PATH} && "
        f"sudo systemctl restart xray && sleep 2 && systemctl is-active xray"
    )
    print(out.strip() or err.strip())
    if code != 0 or "active" not in out:
        print("Restart failed — rolling back")
        ssh_remote(f"sudo cp {backup_path} {CONFIG_PATH} && sudo systemctl restart xray")
        return 1

    print("\n=== 6. Verify stats API + VPN ===")
    code, out, err = ssh_remote(
        f"ss -tlnp | grep {STATS_PORT}; "
        f"sudo xray api statsquery --server=127.0.0.1:{STATS_PORT} --pattern=user 2>&1 | head -c 1500"
    )
    print(out.strip())

    code, out, err = run(client, "cd /opt/qooq-vpn && .venv/bin/python scripts/sync_traffic.py 2>&1")
    print("\nTraffic sync:", out.strip())

    code, out, err = run(client, "curl -s http://127.0.0.1:8000/health")
    print("API health:", out.strip())

    ssh_remote(f"rm -f {remote_tmp}")
    run(client, f"rm -f {local_tmp}")

    client.close()
    print("\nDone — Stats API configured safely")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
