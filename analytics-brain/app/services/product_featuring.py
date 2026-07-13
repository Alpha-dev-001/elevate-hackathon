"""
Proactive Product Featuring — the 6th autopilot trigger. Unlike the other
5 (behavior-driven or catalog-scan-driven), this one fires the moment a
new product is added, before any customer behavior exists at all: Qwen
reads its own catalog/order history and picks the new arrival most likely
to convert, grounded in real category performance, not a guess.

Full design: docs/superpowers/specs/2026-07-11-proactive-featuring-
decision-log-design.md
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.schemas import AgentAction

logger = logging.getLogger(__name__)

# A category needs at least this many recent orders to be "proven" —
# otherwise there's no real signal to ground a featuring decision in.
FEATURING_MIN_CATEGORY_ORDERS = int(os.getenv("FEATURING_MIN_CATEGORY_ORDERS", "1"))
# How far back "recent" category performance looks — a week, not an hour,
# since this isn't a live-anomaly trigger like velocity spike.
FEATURING_WINDOW_HOURS = int(os.getenv("FEATURING_WINDOW_HOURS", str(24 * 7)))


def score_candidates(
    new_products: list[tuple[str, str, float, str]],
    category_stats: dict[str, tuple[float, int]],
) -> list[tuple[str, float, str]]:
    """Pure scoring — grounds each new product against real category
    performance. new_products: (product_id, name, price, category).
    category_stats: category -> (avg_price, recent_order_count).

    Score rewards categories with proven recent orders, penalizes a price
    far from the category's own average (a $400 item in a $20-avg category
    is a mismatch, not a featuring candidate, however many orders that
    category has). Categories with no stats or below the minimum order
    floor are skipped entirely — not comparable, not scored."""
    scored: list[tuple[str, float, str]] = []
    for product_id, name, price, category in new_products:
        avg_price, order_count = category_stats.get(category, (0.0, 0))
        if order_count < FEATURING_MIN_CATEGORY_ORDERS:
            continue
        price_penalty = abs(price - avg_price) / avg_price if avg_price > 0 else 1.0
        score = order_count - price_penalty
        comparison = (
            f'"{name}" (${price:.2f}) enters "{category}" — {order_count} orders '
            f"there in the last {FEATURING_WINDOW_HOURS}h, category averages ${avg_price:.2f}"
        )
        scored.append((product_id, score, comparison))
    return scored


def pick_best_candidate(scored: list[tuple[str, float, str]]) -> tuple[str, str] | None:
    """The single strongest candidate, or None — a batch with no comparable
    category is a correct, quiet no-op, same discipline as
    store_review.pick_underperformer."""
    if not scored:
        return None
    best = max(scored, key=lambda s: s[1])
    return best[0], best[2]


async def evaluate_new_products(
    merchant_id: str, new_product_ids: list[str], db: "AsyncSession", redis
) -> "AgentAction | None":
    """Score newly-added products against real category performance; if one
    stands out, run it through the same decision cycle as every other
    trigger. Called once per batch (single add or CSV import), never once
    per product — the existing one-pending-action gate in
    run_decision_cycle then naturally limits this to at most one proposal
    regardless of batch size. Returns None (not an error) when nothing is
    comparable — a quiet no-op is a correct outcome here."""
    import statistics
    import time
    from collections import defaultdict
    from sqlalchemy import select
    from app.models.db_models import ProductDB, OrderDB

    new_rows = (await db.execute(
        select(ProductDB).where(ProductDB.id.in_(new_product_ids))
    )).scalars().all()
    if not new_rows:
        return None

    # Category stats from the EXISTING catalog/orders — the new products
    # themselves can't have order history yet, so this must be computed
    # from what was already active before this batch landed.
    existing = (await db.execute(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .where(ProductDB.id.notin_(new_product_ids))
    )).scalars().all()

    by_category: dict[str, list[float]] = defaultdict(list)
    category_by_pid: dict[str, str] = {}
    for p in existing:
        category_by_pid[p.id] = p.category or ""
        if p.category and p.price > 0:
            by_category[p.category].append(p.price)

    cutoff = int(time.time() * 1000) - FEATURING_WINDOW_HOURS * 3600 * 1000
    orders = (await db.execute(
        select(OrderDB)
        .where(OrderDB.merchant_id == merchant_id)
        .where(OrderDB.created_at >= cutoff)
    )).scalars().all()

    order_counts: dict[str, int] = defaultdict(int)
    for o in orders:
        for item in (o.items or []):
            pid = item.get("product_id") if isinstance(item, dict) else None
            cat = category_by_pid.get(pid or "")
            if cat:
                order_counts[cat] += 1

    category_stats = {
        cat: (statistics.mean(prices), order_counts.get(cat, 0))
        for cat, prices in by_category.items()
    }

    candidates = [
        (p.id, p.name, p.price, p.category)
        for p in new_rows
        if p.category
    ]
    scored = score_candidates(candidates, category_stats)
    picked = pick_best_candidate(scored)
    if not picked:
        return None
    _product_id, comparison = picked

    from app.services.decision_engine import run_decision_cycle
    return await run_decision_cycle(merchant_id, comparison, db, redis)
