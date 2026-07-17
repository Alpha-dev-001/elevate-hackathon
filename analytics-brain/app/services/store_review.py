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
# Mechanism 3 (swarm coordination design): a product at or below this stock
# level, WITH real view demand (see scarcity_signal_holds), is a genuine
# scarcity-pricing candidate for Pricing Strategist.
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))


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


def scarcity_signal_holds(
    stock: int, recent_views: int, low_stock_threshold: int, demand_threshold: int,
) -> bool:
    """Pure joint-condition check: a real scarcity-pricing opportunity exists
    only when stock is genuinely low AND there's real recent demand (view
    velocity) for the SAME product — either alone is not enough. A merchant
    should never see a price-bump proposal from stock alone, or from view
    interest alone. No I/O."""
    return stock <= low_stock_threshold and recent_views >= demand_threshold


def find_matching_search_insight(product_name: str, insights: list[dict]) -> dict | None:
    """Best-effort supporting color only — a simple case-insensitive
    substring match of a tracked search query against the product name,
    nothing more elaborate. Returns the first hit (insights is already
    sorted most-searched-first by search_tracker.list_search_insights) or
    None. Never gates the scarcity check itself — see scarcity_signal_holds,
    which only looks at stock + view velocity."""
    name_lower = product_name.lower()
    for insight in insights:
        label_lower = insight["label"].lower()
        if label_lower in name_lower or name_lower in label_lower:
            return insight
    return None


def format_scarcity_description(
    product_name: str, stock: int, recent_views: int, search_insight: dict | None,
) -> str:
    """View count leads the sentence (not the product name), same reasoning
    as format_review_description: decision_engine._extract_count() greps
    the first \\d+ for the grounded GMV estimate."""
    demand_note = (
        f", search demand also present ({search_insight['count']}x)"
        if search_insight else ""
    )
    return (
        f"Scarcity signal: {recent_views} recent views on \"{product_name}\" "
        f"with only {stock} left in stock{demand_note} — a scarcity price "
        f"could accelerate conversions before stockout"
    )


async def should_check_scarcity(product_id: str, redis) -> bool:
    """Once-per-UTC-day dedup guard — simpler than pricing_cycle's
    should_run_pricing_check (no escalation streak needed here, just a
    daily gate keyed on today's UTC date string)."""
    from datetime import datetime, timezone
    from app.core.redis import Keys
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return not await redis.exists(Keys.scarcity_checked(product_id, date_str))


async def mark_scarcity_checked(product_id: str, redis) -> None:
    """Marks a product as evaluated-to-a-definite-outcome for the UTC day, so
    it isn't re-evaluated again today. The caller (check_scarcity_signals)
    fires this in exactly two cases — the joint condition didn't hold, or a
    proposal was actually created — but NOT when the signal held yet no
    proposal came back (a transient miss: Qwen declined, or a higher-priority
    card held the one-card slot). Leaving that case unmarked lets the next
    tick retry rather than burning the product's daily slot on a miss that may
    have had nothing to do with this product. Same spirit as pricing_cycle's
    record_pricing_check_result, just gated on outcome rather than
    unconditional."""
    from datetime import datetime, timezone
    from app.core.redis import Keys
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await redis.set(Keys.scarcity_checked(product_id, date_str), "1", ex=90000)  # 25h TTL — covers the day plus margin


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


async def check_scarcity_signals(merchant_id: str, db: "AsyncSession", redis) -> "AgentAction | None":
    """Mechanism 3 (swarm coordination design): proactively looks for a
    product whose stock is genuinely low AND has real recent view demand,
    and if so proposes a scarcity price via Pricing Strategist — the same
    propose_scarcity_price tool the REACTIVE velocity-spike path already
    uses, just triggered proactively instead of only as a side effect of a
    live spike. Runs once per product per UTC day (should_check_scarcity).
    Per-product try/except — one product's failure must not skip the rest,
    matching this file's own established discipline."""
    from sqlalchemy import select
    from app.models.db_models import ProductDB
    from app.services import behavior_tracker
    from app.services.search_tracker import list_search_insights
    from app.services.decision_engine import run_decision_cycle
    from app.services.qwen_roles import PRICING_STRATEGIST

    products = (
        await db.execute(
            select(ProductDB)
            .where(ProductDB.merchant_id == merchant_id)
            .where(ProductDB.is_active == True)
            .where(ProductDB.stock <= LOW_STOCK_THRESHOLD)
        )
    ).scalars().all()
    if not products:
        return None

    per_product_views = await behavior_tracker.count_per_product_views_in_window(redis, merchant_id)

    for product in products:
        try:
            if not await should_check_scarcity(product.id, redis):
                continue
            recent_views = per_product_views.get(product.id, 0)
            if not scarcity_signal_holds(
                product.stock, recent_views, LOW_STOCK_THRESHOLD, behavior_tracker.ANOMALY_THRESHOLD * 4,
            ):
                await mark_scarcity_checked(product.id, redis)
                continue

            insights = await list_search_insights(merchant_id, db)
            search_insight = find_matching_search_insight(product.name, insights)
            description = format_scarcity_description(product.name, product.stock, recent_views, search_insight)
            action = await run_decision_cycle(
                merchant_id, description, db, redis,
                role=PRICING_STRATEGIST, target_product_id=product.id,
            )
            if action:
                await mark_scarcity_checked(product.id, redis)
                return action
            # No action came back — Qwen declined, or (rarely, since priority
            # arbitration usually lets a scarcity signal supersede a
            # lower-priority card) a higher-priority pending card holds the
            # one-card slot this tick. Deliberately NOT marked checked: the
            # joint signal genuinely held, so let the next tick re-evaluate
            # rather than burn this product's once-daily slot on a transient
            # miss. The only cost is re-asking about a product that keeps
            # qualifying yet keeps being declined — a small, self-limiting set
            # whose stock/demand is worth a fresh look hourly anyway.
        except Exception as e:  # noqa: BLE001 — one product's failure must not skip the rest
            logger.warning("[store_review] scarcity check failed for product %s: %s", product.id, e)

    return None


async def run_store_review(
    merchant_id: str, db: "AsyncSession", redis
) -> "AgentAction | None":
    """Duplicate detection runs first — higher autopilot value (signal-driven,
    genuine merge decision) than the other two checks. Call order here is a
    reading-order convenience, not a correctness dependency: the
    priority-arbitration gate in run_decision_cycle (see
    learning.compute_effective_priority) now resolves any real conflict by
    each signal's own priority, not by which check happens to run first in
    this function. See
    docs/superpowers/specs/2026-07-12-duplicate-detection-autopilot-design.md
    and docs/superpowers/specs/2026-07-17-swarm-coordination-design.md.

    Falls through each check in turn when the previous one finds nothing.
    Returns None (no-op, not an error) when every check finds nothing or a
    decision is already pending — a correct, quiet outcome either way."""
    from app.services.duplicate_scan import run_duplicate_scan
    dup_action = await run_duplicate_scan(merchant_id, db, redis)
    if dup_action:
        return dup_action

    scarcity_action = await check_scarcity_signals(merchant_id, db, redis)
    if scarcity_action:
        return scarcity_action

    found = await find_underperformer(merchant_id, db)
    if not found:
        return None
    _, description = found

    from app.services.decision_engine import run_decision_cycle
    from app.services.qwen_roles import STORE_CURATOR
    return await run_decision_cycle(merchant_id, description, db, redis, role=STORE_CURATOR)


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
