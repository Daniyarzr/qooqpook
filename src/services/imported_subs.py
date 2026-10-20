"""Import an external VPN subscription, keep only endpoints that accept TCP."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.utils import utcnow
from src.models import ImportedConfig, ImportedSubscription

logger = logging.getLogger(__name__)

_SCHEMES = ("vless://", "trojan://", "ss://", "hysteria2://", "hy2://")
_MAX_CONFIGS = 80
_PROBE_TIMEOUT = 3.0
_PROBE_CONCURRENCY = 16
_FAILS_BEFORE_DELETE = 2


@dataclass
class ParsedNode:
    uri: str
    host: str
    port: int
    remark: str
    fingerprint: str


def _maybe_decode(body: str) -> str:
    compact = "".join(body.split())
    pad = "=" * (-len(compact) % 4)
    try:
        raw = base64.b64decode(compact + pad, validate=False)
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return body
    if "://" in text:
        return text
    return body


def _fingerprint(uri: str) -> str:
    parsed = urlparse(uri)
    key = f"{parsed.scheme}|{parsed.username}|{parsed.hostname}|{parsed.port}|{parsed.query}"
    return hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()


def parse_node(uri: str) -> ParsedNode | None:
    line = uri.strip()
    if not line.startswith(_SCHEMES):
        return None
    parsed = urlparse(line)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None
    remark = unquote(parsed.fragment or "").strip()
    if len(remark) > 160:
        remark = remark[:160]
    return ParsedNode(
        uri=line,
        host=host[:255],
        port=int(port),
        remark=remark,
        fingerprint=_fingerprint(line),
    )


def parse_subscription_body(body: str) -> list[ParsedNode]:
    text = _maybe_decode(body)
    seen: set[str] = set()
    nodes: list[ParsedNode] = []
    for line in text.splitlines():
        node = parse_node(line)
        if not node or node.fingerprint in seen:
            continue
        seen.add(node.fingerprint)
        nodes.append(node)
        if len(nodes) >= _MAX_CONFIGS:
            break
    return nodes


async def fetch_subscription(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Нужна ссылка http или https")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(
            url.strip(),
            headers={"User-Agent": "QooQ-SubImport/1.0"},
        )
        response.raise_for_status()
        return response.text


async def tcp_ping(host: str, port: int) -> int | None:
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=_PROBE_TIMEOUT,
        )
    except Exception:
        return None
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return max(1, int((time.perf_counter() - started) * 1000))


async def probe_nodes(nodes: list[ParsedNode]) -> dict[str, int | None]:
    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def one(node: ParsedNode) -> tuple[str, int | None]:
        async with sem:
            return node.fingerprint, await tcp_ping(node.host, node.port)

    pairs = await asyncio.gather(*(one(node) for node in nodes))
    return dict(pairs)


async def list_alive_uris(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(ImportedConfig.uri)
        .join(ImportedSubscription, ImportedSubscription.id == ImportedConfig.source_id)
        .where(
            ImportedSubscription.is_active.is_(True),
            ImportedConfig.is_alive.is_(True),
        )
        .order_by(ImportedConfig.id)
    )
    return [row[0] for row in result.all() if row[0]]


async def refresh_source(session: AsyncSession, source_id: int) -> dict[str, int]:
    source = await session.get(ImportedSubscription, source_id)
    if not source:
        raise ValueError("Подписка не найдена")

    stats = {"parsed": 0, "alive": 0, "dead": 0, "removed": 0}
    now = utcnow()
    try:
        body = await fetch_subscription(source.url)
        nodes = parse_subscription_body(body)
    except Exception as exc:
        source.last_error = str(exc)[:500]
        source.last_checked_at = now
        await session.flush()
        raise ValueError(f"Не удалось скачать подписку: {exc}") from exc

    stats["parsed"] = len(nodes)
    if not nodes:
        source.last_error = "В подписке нет VLESS/Trojan/SS ссылок"
        source.last_checked_at = now
        await session.flush()
        raise ValueError(source.last_error)

    pings = await probe_nodes(nodes)
    existing_result = await session.execute(
        select(ImportedConfig).where(ImportedConfig.source_id == source.id)
    )
    existing = {row.fingerprint: row for row in existing_result.scalars().all()}
    seen: set[str] = set()

    for node in nodes:
        seen.add(node.fingerprint)
        ping = pings.get(node.fingerprint)
        row = existing.get(node.fingerprint)
        if row is None:
            row = ImportedConfig(
                source_id=source.id,
                fingerprint=node.fingerprint,
                uri=node.uri,
                host=node.host,
                port=node.port,
            )
            session.add(row)
        row.uri = node.uri
        row.remark = node.remark or f"{node.host}:{node.port}"
        row.host = node.host
        row.port = node.port
        row.last_checked_at = now
        row.last_ping_ms = ping
        if ping is None:
            row.fail_count = int(row.fail_count or 0) + 1
            row.is_alive = False
            stats["dead"] += 1
            if row.fail_count >= _FAILS_BEFORE_DELETE:
                await session.delete(row)
                stats["removed"] += 1
        else:
            row.fail_count = 0
            row.is_alive = True
            stats["alive"] += 1

    for fingerprint, row in existing.items():
        if fingerprint not in seen:
            await session.delete(row)
            stats["removed"] += 1

    source.last_error = None
    source.last_checked_at = now
    await session.flush()
    logger.info("Imported sub %s refresh %s", source.id, stats)
    return stats


async def refresh_active_sources(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(ImportedSubscription).where(ImportedSubscription.is_active.is_(True))
    )
    totals = {"sources": 0, "alive": 0, "dead": 0, "removed": 0, "errors": 0}
    for source in result.scalars().all():
        totals["sources"] += 1
        try:
            stats = await refresh_source(session, source.id)
            totals["alive"] += stats["alive"]
            totals["dead"] += stats["dead"]
            totals["removed"] += stats["removed"]
        except ValueError:
            totals["errors"] += 1
            logger.warning("Imported sub %s refresh failed", source.id)
    return totals


async def list_sources(session: AsyncSession) -> list[ImportedSubscription]:
    result = await session.execute(
        select(ImportedSubscription)
        .options(selectinload(ImportedSubscription.configs))
        .order_by(ImportedSubscription.id.desc())
    )
    return list(result.scalars().unique().all())
