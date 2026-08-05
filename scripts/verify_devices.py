import os
import sys
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("148.135.184.188", username="root", password=os.environ["DEPLOY_PASSWORD"], timeout=15)
cmds = [
    "cd /opt/qooq-vpn && .venv/bin/python scripts/sync_xray_users.py 2>&1 | tail -3",
    """sudo -u postgres psql -d qooq_vpn -c "SELECT sd.id, sd.subscription_id, sd.name, u.id as user_id FROM subscription_devices sd JOIN subscriptions s ON s.id=sd.subscription_id JOIN users u ON u.id=s.user_id;" """,
    "systemctl is-active qooq-api qooq-admin qooq-bot",
]
for cmd in cmds:
    print(">>>", cmd[:60])
    _, o, e = c.exec_command(cmd, timeout=60)
    print(o.read().decode())
    err = e.read().decode()
    if err and "Permission denied" not in err:
        print("ERR", err)
c.close()
