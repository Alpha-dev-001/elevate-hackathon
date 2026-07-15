"""
Graduated autonomy for PRICE_REBALANCE — a trust counter per (merchant,
product) built from realized outcomes of approved price moves. Below
TRUST_STREAK_THRESHOLD every proposal gates (normal option-card flow); at or
above it, a move within a modest band auto-applies without a human gate.

Trust never widens the allowed range — should_auto_apply only decides
whether a move ALREADY inside the interceptor's floor/ceiling (i.e.
clamped_price, the output of enforce_price_rebalance) needs a human gate. A
trusted product can never move further than an untrusted one could have with
approval; trust only removes the gate, never the limit.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.schemas import BusinessConstraints

logger = logging.getLogger(__name__)

TRUST_STREAK_THRESHOLD = 3
AUTO_APPLY_BAND_PERCENT = 10.0


def next_streak(current_streak: int, *, approved: bool, outcome_negative: bool) -> int:
    """Pure streak-transition rule. approved+not-negative increments;
    dismissed OR approved+negative resets to 0 — trust is lost faster than
    it's earned, deliberately."""
    if approved and not outcome_negative:
        return current_streak + 1
    return 0


def should_auto_apply(
    streak: int,
    clamped_price: float,
    baseline_price: float,
    constraints: "BusinessConstraints",
) -> bool:
    """clamped_price MUST already be the interceptor-clamped value (the
    output of enforce_price_rebalance), never Qwen's raw ask — this check
    runs AFTER the floor/ceiling clamp, not instead of it. Upward moves are
    additionally capped by the merchant's own max_uplift_percent (so a 5%
    ceiling means the effective band is min(10%, 5%) = 5%, not a flat 10%
    regardless of what the merchant authorized); downward moves are already
    floor-clamped by enforce_price_rebalance (margin floor / below-cost
    block), so the flat 10% band applies directly."""
    if streak < TRUST_STREAK_THRESHOLD or baseline_price <= 0:
        return False
    move_percent = (clamped_price - baseline_price) / baseline_price * 100
    if move_percent > 0:
        effective_band = min(AUTO_APPLY_BAND_PERCENT, constraints.max_uplift_percent)
    else:
        effective_band = AUTO_APPLY_BAND_PERCENT
    return abs(move_percent) <= effective_band


async def get_trust_streak(
    merchant_id: str, product_id: str, action_type: str, db: "AsyncSession"
) -> int:
    """Missing row == streak 0 == always gates; never defaults to trusted."""
    from sqlalchemy import select
    from app.models.db_models import AutopilotTrustDB

    row = await db.scalar(
        select(AutopilotTrustDB)
        .where(AutopilotTrustDB.merchant_id == merchant_id)
        .where(AutopilotTrustDB.product_id == product_id)
        .where(AutopilotTrustDB.action_type == action_type)
    )
    return row.streak if row else 0


async def update_trust_streak(
    merchant_id: str, product_id: str, action_type: str, db: "AsyncSession",
    *, approved: bool, outcome_negative: bool,
) -> int:
    """Read-modify-write the streak via next_streak, upserting the row.
    Called from two places: outcome_observer.observe_outcome (immediate
    reset on dismissal) and pricing_cycle.evaluate_trust_outcomes (real
    purchase-based outcome for an executed move, evaluated on the daily
    pricing tick once enough product_price_history data exists). Returns the
    new streak value."""
    from sqlalchemy import select
    from app.models.db_models import AutopilotTrustDB

    row = await db.scalar(
        select(AutopilotTrustDB)
        .where(AutopilotTrustDB.merchant_id == merchant_id)
        .where(AutopilotTrustDB.product_id == product_id)
        .where(AutopilotTrustDB.action_type == action_type)
    )
    current = row.streak if row else 0
    new_streak = next_streak(current, approved=approved, outcome_negative=outcome_negative)

    if row:
        row.streak = new_streak
        row.updated_at = int(time.time() * 1000)
    else:
        db.add(AutopilotTrustDB(
            id=str(uuid.uuid4()), merchant_id=merchant_id, product_id=product_id,
            action_type=action_type, streak=new_streak,
        ))
    await db.commit()
    logger.info(
        "[autopilot_trust] %s/%s/%s streak %d -> %d",
        merchant_id, product_id, action_type, current, new_streak,
    )
    return new_streak
