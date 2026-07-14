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


def format_history_summary(rows: list[dict]) -> str:
    """rows: [{"date","views","cart_adds","purchases","price_active",
    "signal_quality"}, ...]. Suspect-flagged days are excluded — Qwen
    reasons over fewer, trusted data points rather than a "corrected"
    number (see pricing_signals.flag_suspicious_signals)."""
    trusted = [r for r in rows if r.get("signal_quality") != "suspect"]
    if not trusted:
        return "no trusted history yet"
    return "; ".join(
        f"{r['date']}: {r['views']} views, {r['cart_adds']} cart-adds, "
        f"{r['purchases']} purchases at ${r['price_active']:.2f}"
        for r in trusted
    )


def compute_magnitude(action_type: str, payload: dict, baseline_price: float | None) -> float | None:
    """The 'how far' number to compare across differently-shaped actions:
    discount_percent for discount-bearing types, or the % move from
    baseline_price for price_rebalance. None if the shape doesn't match."""
    if action_type == "price_rebalance":
        if baseline_price and baseline_price > 0 and "new_price" in payload:
            return abs((payload["new_price"] - baseline_price) / baseline_price * 100)
        return None
    if "discount_percent" in payload:
        return float(payload["discount_percent"])
    return None


def build_revealed_preference_summary(actions: list[dict]) -> str:
    """actions: [{"action_type","status","payload"}, ...] for one merchant,
    trailing window already applied by the caller. status == 'executed' is
    the approved bucket, 'dismissed' is the dismissed bucket — see this
    task's docstring-level note on why AgentActionDB.status stands in for a
    joined outcome-positive flag. Returns "" when there's not enough data."""
    approved, dismissed = [], []
    for a in actions:
        mag = compute_magnitude(a["action_type"], a.get("payload", {}), a.get("baseline_price"))
        if mag is None:
            continue
        if a["status"] == "executed":
            approved.append(mag)
        elif a["status"] == "dismissed":
            dismissed.append(mag)

    if not approved and not dismissed:
        return ""
    parts = []
    if approved:
        parts.append(f"approved moves up to {max(approved):.0f}%")
    if dismissed:
        parts.append(f"dismissed a proposed {min(dismissed):.0f}% move")
    return "this merchant has " + " and ".join(parts) + "."


PRICING_PROMPT = """You are the autonomous pricing brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}

Product under review: {product_name} — baseline price ${baseline_price:.2f}, \
current live price ${current_price:.2f}, unit cost ${cost_price:.2f}.
Recent history (last 7 days): {history_summary}
{comparable_block}{memory_block}
Reason step by step about whether the live price should move, and if so to
where, within your authorized range around the baseline. Call the
propose_price_rebalance tool to act, or make no tool call at all if the
current price is already right. Include your reasoning in your message —
cite the specific signals driving your call.

Never propose a price for a product with no history and no valid comparable —
if you have no real data to reason from, do not call the tool."""


def compose_pricing_prompt(
    *,
    store_name: str,
    mood: str,
    brand_voice: str,
    product_name: str,
    baseline_price: float,
    current_price: float,
    cost_price: float,
    history_summary: str,
    comparable_summary: str = "",
    memory_context: str = "",
) -> str:
    """Pure — no I/O, mirrors compose_decision_prompt's shape exactly."""
    comparable_block = (
        f"\nA similar product's recent performance, for reference since this "
        f"product is new: {comparable_summary}\n"
        if comparable_summary else ""
    )
    memory_block = (
        f"\nPrior outcomes for this store (learn from them): {memory_context}\n"
        if memory_context else ""
    )
    return PRICING_PROMPT.format(
        store_name=store_name, mood=mood, brand_voice=brand_voice,
        product_name=product_name, baseline_price=baseline_price,
        current_price=current_price, cost_price=cost_price,
        history_summary=history_summary,
        comparable_block=comparable_block, memory_block=memory_block,
    )
