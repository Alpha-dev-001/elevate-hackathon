"""
Pricing core — one place that decides what a product actually costs right now.

Everything downstream (storefront display, cart snapshot, order totals) reads
the effective price through here, so a promo can never be honored inconsistently
in one surface and not another. Promo expiry is checked at read time against a
caller-supplied `now` — stale SystemState can never resurrect an expired promo.
"""
from __future__ import annotations

import time

from app.models.schemas import Promo


def now_ms() -> int:
    return int(time.time() * 1000)


def best_active_promo(
    product_id: str,
    active_promos: dict[str, Promo],
    now: int | None = None,
) -> Promo | None:
    """The deepest still-valid discount for a product, or None.

    active_promos is keyed by promo id (SystemState shape). We filter to this
    product's non-expired promos and pick the largest discount.
    """
    now = now_ms() if now is None else now
    candidates = [
        p
        for p in active_promos.values()
        # "all" is a store-wide promo (e.g. a cart-recovery "everything 10% off")
        if (p.product_id == product_id or p.product_id == "all")
        and p.expires_at > now and p.discount_percent > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.discount_percent)


def effective_price(
    base_price: float,
    promo: Promo | None,
    baseline_price: float | None = None,
) -> tuple[float, float | None, str | None]:
    """Returns (price, compare_at, label).

    With an active promo: unchanged from before — (discounted, base_price,
    promo.label), baseline_price is irrelevant once a promo is active.

    With no active promo and baseline_price given: a dynamic-pricing autopilot
    move BELOW baseline gets the same strike-through treatment as a promo
    (compare_at = baseline_price, no label — asymmetric by design, see the
    dynamic-baseline-pricing spec's "UI treatment" section). A move AT or
    ABOVE baseline renders as a plain price — no compare_at, no label, no
    promotional styling for a price increase.

    With no promo and no baseline_price (every pre-existing caller that
    doesn't pass it): unchanged — (base_price, None, None).
    """
    if promo is not None and promo.discount_percent > 0:
        discounted = round(base_price * (1 - promo.discount_percent / 100), 2)
        # Never let rounding push the shown price to/above the original.
        if discounted < base_price:
            return discounted, round(base_price, 2), promo.label

    if baseline_price is not None and base_price < baseline_price:
        return round(base_price, 2), round(baseline_price, 2), None

    return round(base_price, 2), None, None


def margin_floor_price(
    cost_price: float,
    min_margin_percent: float,
    min_price_override: float = 0.0,
) -> float:
    """Lowest price that still respects the margin floor (and any per-product
    minimum the merchant set). The interceptor clamps up to this."""
    margin_price = cost_price * (1 + min_margin_percent / 100)
    return round(max(min_price_override, margin_price), 2)
