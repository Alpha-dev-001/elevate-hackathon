"""
Cart-dwell nudge — a customer who added to cart and then went quiet (no
abandon event yet, still within the session) gets a gentle "complete your
order" nudge before they actually leave. A distinct FUNNEL PHASE from
cart-abandon recovery (dwell = still in session, "buy now"; abandon =
actually left, "come back") — not a competing trigger. run_decision_cycle's
existing one-pending-action-per-merchant gate already makes "whichever fires
first blocks the other" true for free (the same mechanism that already
prioritizes duplicate-scan over the underperformer check in store_review.py)
— nothing new is needed here for that property.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING

from app.core.redis import Keys, get_redis

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CART_DWELL_MINUTES = int(os.getenv("CART_DWELL_MINUTES", "8"))
CART_DWELL_CHECK_INTERVAL_SECONDS = int(os.getenv("CART_DWELL_CHECK_INTERVAL_SECONDS", "60"))


def is_dwelling(cart_updated_at_ms: int, has_items: bool, now_ms: int | None = None) -> bool:
    """Pure — no I/O. A cart with items whose last mutation is at least
    CART_DWELL_MINUTES old is dwelling."""
    if not has_items:
        return False
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return (now_ms - cart_updated_at_ms) >= CART_DWELL_MINUTES * 60 * 1000


async def session_has_abandoned(redis: "Redis", merchant_id: str, session_id: str) -> bool:
    """Scan this merchant's event list for an abandon event from this
    specific session. Keys.events is per-merchant (all event types mixed
    together), not per-session — the only per-session signal durably
    available without adding a new event-recording path (the alternate
    Keys.session_events list is confirmed dead code, unreferenced by any
    router)."""
    raw_events = await redis.lrange(Keys.events(merchant_id), 0, -1)
    for raw in raw_events:
        try:
            ev = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if ev.get("session_id") == session_id and ev.get("event_type") == "abandon":
            return True
    return False


async def run_dwell_check(db: "AsyncSession", redis: "Redis") -> int:
    """One pass per live merchant: for each session with a non-empty cart
    (Keys.active_carts), fire a decision cycle if it's dwelling and hasn't
    abandoned yet. Per-session try/except, per-merchant try/except."""
    from sqlalchemy import select
    from app.models.db_models import MerchantDB
    from app.services import cart as cart_svc
    from app.services.decision_engine import run_decision_cycle

    fired = 0
    merchants = (
        await db.execute(select(MerchantDB).where(MerchantDB.is_live == True))
    ).scalars().all()

    for merchant in merchants:
        try:
            session_ids = await redis.smembers(Keys.active_carts(merchant.id))
            for session_id in session_ids:
                try:
                    cart = await cart_svc.get_cart(merchant.id, session_id)
                    if not is_dwelling(cart.updated_at, bool(cart.items)):
                        continue
                    if await session_has_abandoned(redis, merchant.id, session_id):
                        continue

                    action = await run_decision_cycle(
                        merchant.id,
                        f"Cart dwell: an item has sat in a customer's cart for "
                        f"{CART_DWELL_MINUTES}+ minutes without completing checkout",
                        db, redis,
                        session_id=session_id,
                    )
                    if action:
                        fired += 1
                except Exception as e:  # noqa: BLE001 — one session's failure must not skip the rest
                    logger.warning("[cart_dwell] check failed for session %s: %s", session_id, e)
        except Exception as e:  # noqa: BLE001 — one merchant's failure must not skip the rest
            logger.warning("[cart_dwell] cycle failed for merchant %s: %s", merchant.id, e)

    return fired


def start_dwell_background_loop() -> None:
    """Same in-process asyncio loop shape as store_review.py, on a much
    tighter cadence (60s default) — dwell needs to be checked well inside
    CART_DWELL_MINUTES to matter."""
    import asyncio

    async def _tick():
        from app.core.database import get_session_factory
        factory = get_session_factory()
        try:
            async with factory() as db:
                redis = await get_redis()
                fired = await run_dwell_check(db, redis)
                if fired:
                    logger.info("[cart_dwell] %d dwell nudge(s) fired this tick", fired)
        except Exception as e:  # noqa: BLE001 — a failed tick must not kill the loop
            logger.warning("[cart_dwell] tick failed: %s", e)

    async def _runner():
        while True:
            await asyncio.sleep(CART_DWELL_CHECK_INTERVAL_SECONDS)
            await _tick()

    asyncio.create_task(_runner())
    logger.info(
        "[cart_dwell] background loop started (every %ss)", CART_DWELL_CHECK_INTERVAL_SECONDS,
    )
