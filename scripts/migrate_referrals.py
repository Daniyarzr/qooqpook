#!/usr/bin/env python3
"""Migrate referral relationships from legacy SQLite to QooQ VPN."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paramiko
from sqlalchemy import select

from src.db.session import async_session_factory
from src.models import User
from src.repositories import UserRepository

logger = logging.getLogger("migrate_referrals")

OLD_SQLITE_PATH = os.environ.get("OLD_SQLITE_PATH", "/opt/vpn_bot/vpn_database.db")

LEGACY_REFERRERS = """
SELECT telegram_id, referrer_id
FROM users
WHERE referrer_id IS NOT NULL
  AND referrer_id != ''
  AND CAST(referrer_id AS INTEGER) != 0
ORDER BY telegram_id
"""


def _ssh_password() -> str:
    password = os.environ.get("OLD_SSH_PASSWORD", "")
    if not password:
        raise SystemExit("Set OLD_SSH_PASSWORD environment variable")
    return password


def fetch_legacy_referrals() -> list[tuple[int, int]]:
    host = os.environ.get("OLD_SSH_HOST", "82.21.153.119")
    user = os.environ.get("OLD_SSH_USER", "root")
    one_line = " ".join(LEGACY_REFERRERS.split()).replace('"', '\\"')
    cmd = f'sqlite3 -separator "|" {OLD_SQLITE_PATH} "{one_line}"'

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=_ssh_password(), timeout=30)
    _, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    if err.strip():
        raise RuntimeError(err)

    rows: list[tuple[int, int]] = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 2:
            continue
        try:
            tg_id = int(parts[0])
            referrer_tg_id = int(parts[1])
        except ValueError:
            continue
        if tg_id == referrer_tg_id:
            continue
        rows.append((tg_id, referrer_tg_id))
    return rows


async def migrate(*, dry_run: bool) -> int:
    legacy_rows = fetch_legacy_referrals()
    logger.info("Legacy referral links: %d", len(legacy_rows))

    updated = 0
    skipped = 0
    missing = 0

    async with async_session_factory() as session:
        repo = UserRepository(session)
        tg_to_user: dict[int, User] = {}

        async def get_user(telegram_id: int) -> User | None:
            if telegram_id in tg_to_user:
                return tg_to_user[telegram_id]
            user = await repo.get_by_telegram_id(telegram_id)
            if user:
                tg_to_user[telegram_id] = user
            return user

        for tg_id, referrer_tg_id in legacy_rows:
            user = await get_user(tg_id)
            referrer = await get_user(referrer_tg_id)
            if not user or not referrer:
                missing += 1
                logger.warning("Skip tg=%s referrer_tg=%s (user missing in new DB)", tg_id, referrer_tg_id)
                continue
            if user.referred_by_id:
                skipped += 1
                continue
            if dry_run:
                logger.info("[dry-run] tg=%s -> referrer #%s (tg %s)", tg_id, referrer.id, referrer_tg_id)
                updated += 1
                continue
            user.referred_by_id = referrer.id
            updated += 1
            logger.info("Linked tg=%s -> referrer #%s (tg %s)", tg_id, referrer.id, referrer_tg_id)

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    logger.info("Done: updated=%d skipped=%d missing=%d", updated, skipped, missing)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Migrate legacy referral links")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
