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


async def count_per_product_views_in_window(
    redis: "Redis", merchant_id: str
) -> dict[str, int]:
    """Count view events per product in the last ANOMALY_WINDOW_SECONDS seconds.

    Returns a dict mapping product_id to view count. Used to identify which
    specific product is spiking so the decision cycle can target it.
    """
    from app.core.redis import Keys
    key = Keys.events(merchant_id)
    raw_events = await redis.lrange(key, 0, 99)
    now = time.time()
    counts: dict[str, int] = {}
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            if (
                ev.get("event_type") == "view"
                and ev.get("product_id")
                and now - float(ev.get("timestamp", 0)) < ANOMALY_WINDOW_SECONDS
            ):
                pid = ev["product_id"]
                counts[pid] = counts.get(pid, 0) + 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return counts


def anomaly_description(
    abandon_count: int,
    view_count: int,
    per_product_views: dict[str, int] | None = None,
) -> tuple[str | None, str | None]:
    """Return (anomaly_description, spiking_product_id) or (None, None) if no anomaly.

    For velocity spikes, identifies the specific product with the most views
    so the decision cycle can target it. The product_id is returned separately
    so the caller can look up the product name and enrich the description.
    """
    if abandon_count >= ANOMALY_THRESHOLD:
        return (
            f"Cart abandon surge: {abandon_count} abandons in {ANOMALY_WINDOW_SECONDS}s — customers are leaving without buying",
            None,  # abandon surge is store-wide, no single product
        )
    if view_count >= ANOMALY_THRESHOLD * 4:
        # Identify the spiking product — the one with the most views
        spiking_product_id = None
        if per_product_views:
            spiking_product_id = max(per_product_views, key=per_product_views.get)
            spiking_views = per_product_views[spiking_product_id]
            return (
                f"Velocity spike: {spiking_views} views on product {spiking_product_id} in {ANOMALY_WINDOW_SECONDS}s — that product is going viral",
                spiking_product_id,
            )
        # Fallback: no per-product data, use store-wide count
        return (
            f"Velocity spike: {view_count} views in {ANOMALY_WINDOW_SECONDS}s — products going viral",
            None,
        )
    return (None, None)
