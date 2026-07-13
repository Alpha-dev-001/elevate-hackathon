"""
Proactive Store Review — Qwen scans the catalog without waiting for an
anomaly. Reactive decisions (velocity spike, cart-abandon surge) only fire
when a customer does something unusual; a quiet store with a real problem
never gets Qwen's attention. This closes that gap.

Signal: a product with real view interest (Redis product_velocity, the
same counter the reactive path reads) but zero completed orders in the
review window (Postgres — the durable, real conversion record, not an
estimate). High interest + no conversion is a genuine "something is off"
read a merchant would want flagged: bad photo, weak description, priced
wrong, wrong category.

Same decision engine as the reactive/recovery paths (run_decision_cycle) —
only the anomaly description differs. No new Qwen call shape, no new
tool, no new interceptor path. One more honest trigger into the one
cognitive loop.
"""
from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

from app.core.redis import get_redis, Keys

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.schemas import AgentAction

logger = logging.getLogger(__name__)

# Env-configurable, same pattern as ANOMALY_THRESHOLD (behavior_tracker.py).
STORE_REVIEW_WINDOW_HOURS = int(os.getenv("STORE_REVIEW_WINDOW_HOURS", "24"))
STORE_REVIEW_MIN_VIEWS = int(os.getenv("STORE_REVIEW_MIN_VIEWS", "5"))
STORE_REVIEW_INTERVAL_SECONDS = int(os.getenv("STORE_REVIEW_INTERVAL_SECONDS", "3600"))


def extract_ordered_product_ids(order_items_list: list[list[dict] | None]) -> set[str]:
    """Flatten a list of orders' `items` JSON blobs into the set of product_ids
    that have at least one completed order. Pure — no DB/Redis, easy to test."""
    ids: set[str] = set()
    for items in order_items_list:
        for item in items or []:
            pid = item.get("product_id") if isinstance(item, dict) else None
            if pid:
                ids.add(pid)
    return ids


def pick_underperformer(
    velocity_data: list[tuple[str, float]],
    ordered_product_ids: set[str],
    min_views: int = STORE_REVIEW_MIN_VIEWS,
) -> str | None:
    """The selection rule, isolated from I/O: the highest-viewed product_id
    that has zero orders and clears the minimum view bar, or None.

    velocity_data must already be sorted descending by views (Redis
    `zrevrange` returns it that way) — the moment one candidate falls below
    min_views, nothing after it can qualify either, so we stop there rather
    than scanning the whole list.
    """
    for product_id, views in velocity_data:
        if views < min_views:
            break
        if product_id not in ordered_product_ids:
            return product_id
    return None


def format_review_description(product_name: str, views: float, window_hours: int = STORE_REVIEW_WINDOW_HOURS) -> str:
    """View count leads the sentence (not the product name) so
    decision_engine._extract_count() — which greps the first \\d+ for the
    grounded GMV estimate — can't grab a digit from a product name like
    'AirPods 2' instead of the real view count."""
    return (
        f"Store review: {int(views)} views, 0 orders in the last "
        f'{window_hours}h for "{product_name}" — high interest, no conversion'
    )


async def find_underperformer(
    merchant_id: str, db: "AsyncSession"
) -> tuple[str, str] | None:
    """Return (product_id, review_description) for the most view-heavy active
    product with zero orders in the window, or None if nothing stands out.

    Deliberately conservative — a clean catalog returns None. This is a
    proactive nudge, not a forced action every cycle. Thin I/O wrapper —
    the actual selection logic is pick_underperformer(), tested directly.
    """
    from sqlalchemy import select
    from app.models.db_models import OrderDB, ProductDB

    redis = await get_redis()
    velocity_data = await redis.zrevrange(
        Keys.product_velocity(merchant_id), 0, -1, withscores=True
    )
    if not velocity_data:
        return None

    cutoff = int(time.time() * 1000) - STORE_REVIEW_WINDOW_HOURS * 3600 * 1000
    orders = (
        await db.execute(
            select(OrderDB)
            .where(OrderDB.merchant_id == merchant_id)
            .where(OrderDB.created_at >= cutoff)
        )
    ).scalars().all()
    ordered_product_ids = extract_ordered_product_ids([o.items for o in orders])

    # pick_underperformer only guarantees "zero orders + enough views" — it
    # has no product data, so it can pick something inactive/deleted. Walk
    # candidates in order and confirm the product is still real and active
    # before accepting one (a handful of DB lookups at most, never the
    # whole velocity list on a healthy catalog).
    for product_id, views in velocity_data:
        if views < STORE_REVIEW_MIN_VIEWS:
            break
        if product_id in ordered_product_ids:
            continue
        product = await db.get(ProductDB, product_id)
        if not product or not product.is_active:
            continue
        return product_id, format_review_description(product.name, views)

    return None


async def run_store_review(
    merchant_id: str, db: "AsyncSession", redis
) -> "AgentAction | None":
    """Duplicate detection runs first — higher autopilot value (signal-driven,
    genuine merge decision) than the underperformer check. See
    docs/superpowers/specs/2026-07-12-duplicate-detection-autopilot-design.md.
    run_decision_cycle's one-pending-action gate means only one of
    {duplicate, underperformer} can fire a card per tick anyway, so checking
    duplicates first simply prioritizes it.

    Falls through to the underperformer check when duplicates find nothing.
    Returns None (no-op, not an error) when both checks find nothing or a
    decision is already pending — a correct, quiet outcome either way."""
    from app.services.duplicate_scan import run_duplicate_scan
    dup_action = await run_duplicate_scan(merchant_id, db, redis)
    if dup_action:
        return dup_action

    found = await find_underperformer(merchant_id, db)
    if not found:
        return None
    _, description = found

    from app.services.decision_engine import run_decision_cycle
    return await run_decision_cycle(merchant_id, description, db, redis)


def start_background_loop() -> None:
    """Periodic proactive review across every live merchant. In-process
    asyncio timer — same tradeoff as outcome_observer.schedule_observation
    (fine for the demo; a durable scheduler is the production path)."""
    import asyncio

    async def _tick():
        from sqlalchemy import select
        from app.core.database import get_session_factory
        from app.models.db_models import MerchantDB

        factory = get_session_factory()
        try:
            async with factory() as db:
                redis = await get_redis()
                merchants = (
                    await db.execute(select(MerchantDB).where(MerchantDB.is_live == True))
                ).scalars().all()
                for merchant in merchants:
                    try:
                        action = await run_store_review(merchant.id, db, redis)
                        if action:
                            logger.info(
                                "[store_review] proactive action for %s: %s",
                                merchant.id, action.action_type,
                            )
                    except Exception as e:  # noqa: BLE001 — one merchant's failure must not skip the rest
                        logger.warning("[store_review] cycle failed for %s: %s", merchant.id, e)
        except Exception as e:  # noqa: BLE001 — a failed tick must not kill the loop
            logger.warning("[store_review] tick failed: %s", e)

    async def _runner():
        while True:
            await asyncio.sleep(STORE_REVIEW_INTERVAL_SECONDS)
            await _tick()

    asyncio.create_task(_runner())
    logger.info(
        "[store_review] background loop started (every %ss)",
        STORE_REVIEW_INTERVAL_SECONDS,
    )
