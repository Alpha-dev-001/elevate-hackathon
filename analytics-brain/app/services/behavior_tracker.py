"""
Behavior event ingestion and anomaly threshold checking.
Anomaly detection is deterministic (env-var thresholds) — no statistics.
"""
from __future__ import annotations

import json
import os
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLD = int(os.getenv("ANOMALY_THRESHOLD", "5"))
ANOMALY_WINDOW_SECONDS = int(os.getenv("ANOMALY_WINDOW_SECONDS", "30"))


async def push_event(redis: "Redis", merchant_id: str, event: dict) -> None:
    """Append a behavior event to the Redis list and trim to 500."""
    from app.core.redis import Keys, TTL
    key = Keys.events(merchant_id)
    await redis.lpush(key, json.dumps(event))
    await redis.ltrim(key, 0, 499)
    await redis.expire(key, TTL.EVENTS)


async def count_abandons_in_window(redis: "Redis", merchant_id: str) -> int:
    """Count abandon events in the last ANOMALY_WINDOW_SECONDS seconds."""
    from app.core.redis import Keys
    key = Keys.events(merchant_id)
    raw_events = await redis.lrange(key, 0, 99)
    now = time.time()
    count = 0
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            if (
                ev.get("event_type") == "abandon"
                and now - float(ev.get("timestamp", 0)) < ANOMALY_WINDOW_SECONDS
            ):
                count += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return count


async def count_views_in_window(redis: "Redis", merchant_id: str) -> int:
    """Count view events in the last ANOMALY_WINDOW_SECONDS seconds."""
    from app.core.redis import Keys
    key = Keys.events(merchant_id)
    raw_events = await redis.lrange(key, 0, 99)
    now = time.time()
    count = 0
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            if (
                ev.get("event_type") == "view"
                and now - float(ev.get("timestamp", 0)) < ANOMALY_WINDOW_SECONDS
            ):
                count += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return count


def anomaly_description(abandon_count: int, view_count: int) -> str | None:
    """Return a human-readable anomaly description or None if no anomaly."""
    if abandon_count >= ANOMALY_THRESHOLD:
        return f"Cart abandon surge: {abandon_count} abandons in {ANOMALY_WINDOW_SECONDS}s — customers are leaving without buying"
    if view_count >= ANOMALY_THRESHOLD * 4:
        return f"Velocity spike: {view_count} views in {ANOMALY_WINDOW_SECONDS}s — products going viral"
    return None
