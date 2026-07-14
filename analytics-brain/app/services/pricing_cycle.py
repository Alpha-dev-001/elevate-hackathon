"""
Dynamic baseline pricing — the daily reasoning cycle. A merchant-set
baseline_price stays fixed while Qwen continuously reasons about where the
LIVE price should sit in a bounded range around it, using each product's own
durable history (product_price_history, see pricing_signals.py) and, when a
product is too new to have its own, a borrowed comparable's history.

No price move is ever based on zero data — is_price_rebalance_eligible is the
hard gate: below it, propose_price_rebalance isn't even offered as a tool.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.db_models import ProductDB

logger = logging.getLogger(__name__)

# A comparable must be within this fraction of the new product's baseline
# price to be a meaningful reference point — not a tuned constant, just the
# spec's own "±30%" decision.
COMPARABLE_PRICE_BAND = 0.30


def is_price_rebalance_eligible(history_row_count: int, purchase_count: int) -> bool:
    """Cold-start gate: ≥3 days of product_price_history rows, OR ≥1
    purchase — whichever comes first. Pure — no I/O, easy to test."""
    return history_row_count >= 3 or purchase_count >= 1


def select_comparable_product(
    baseline_price: float, category: str, candidates: list[dict],
) -> str | None:
    """Pure selection over already-fetched candidate summaries (each a dict
    with product_id/category/baseline_price/history_row_count/purchase_count).
    Same category, within ±30% baseline_price, and past ITS OWN cold-start
    threshold (a donor must itself be a proven product). Picks the closest
    baseline_price match. This narrows the field to valid candidates only —
    Qwen decides whether/how to use the comparable's history in the prompt,
    this is not an algorithmic similarity formula beyond that filter."""
    if baseline_price <= 0:
        return None
    valid = [
        c for c in candidates
        if c["category"] == category
        and abs(c["baseline_price"] - baseline_price) / baseline_price <= COMPARABLE_PRICE_BAND
        and is_price_rebalance_eligible(c["history_row_count"], c["purchase_count"])
    ]
    if not valid:
        return None
    return min(valid, key=lambda c: abs(c["baseline_price"] - baseline_price))["product_id"]


async def check_eligibility(product_id: str, db: "AsyncSession") -> bool:
    """I/O wrapper: pulls the two counts is_price_rebalance_eligible needs."""
    from sqlalchemy import select, func
    from app.models.db_models import ProductPriceHistoryDB

    row_count = await db.scalar(
        select(func.count())
        .select_from(ProductPriceHistoryDB)
        .where(ProductPriceHistoryDB.product_id == product_id)
    )
    purchase_sum = await db.scalar(
        select(func.sum(ProductPriceHistoryDB.purchases))
        .where(ProductPriceHistoryDB.product_id == product_id)
    )
    return is_price_rebalance_eligible(int(row_count or 0), int(purchase_sum or 0))


async def find_comparable(product: "ProductDB", db: "AsyncSession") -> str | None:
    """I/O wrapper: fetches same-category active products in this merchant's
    catalog, builds each one's eligibility summary, and delegates the actual
    selection to the pure select_comparable_product."""
    from sqlalchemy import select, func
    from app.models.db_models import ProductDB, ProductPriceHistoryDB

    if not product.category:
        return None

    rows = (
        await db.execute(
            select(ProductDB)
            .where(ProductDB.merchant_id == product.merchant_id)
            .where(ProductDB.id != product.id)
            .where(ProductDB.is_active == True)
            .where(ProductDB.category == product.category)
        )
    ).scalars().all()

    candidates: list[dict] = []
    for c in rows:
        row_count = await db.scalar(
            select(func.count())
            .select_from(ProductPriceHistoryDB)
            .where(ProductPriceHistoryDB.product_id == c.id)
        )
        purchase_sum = await db.scalar(
            select(func.sum(ProductPriceHistoryDB.purchases))
            .where(ProductPriceHistoryDB.product_id == c.id)
        )
        candidates.append({
            "product_id": c.id, "category": c.category,
            "baseline_price": c.baseline_price,
            "history_row_count": int(row_count or 0),
            "purchase_count": int(purchase_sum or 0),
        })

    return select_comparable_product(product.baseline_price, product.category, candidates)
