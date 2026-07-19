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
    auto_apply_enabled: bool,
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
    block), so the flat 10% band applies directly.

    A qualifying streak is necessary but never sufficient — auto_apply_enabled
    is a separate, merchant-set choice (see AutopilotTrustDB's own docstring).
    Earning trust unlocks the option; it never flips the switch itself."""
    if not auto_apply_enabled or streak < TRUST_STREAK_THRESHOLD or baseline_price <= 0:
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


async def get_trust_state(
    merchant_id: str, product_id: str, action_type: str, db: "AsyncSession"
) -> tuple[int, bool]:
    """(streak, auto_apply_enabled) — the pair should_auto_apply actually
    needs. Missing row == (0, False), same "never defaults to trusted"
    guarantee as get_trust_streak."""
    from sqlalchemy import select
    from app.models.db_models import AutopilotTrustDB

    row = await db.scalar(
        select(AutopilotTrustDB)
        .where(AutopilotTrustDB.merchant_id == merchant_id)
        .where(AutopilotTrustDB.product_id == product_id)
        .where(AutopilotTrustDB.action_type == action_type)
    )
    return (row.streak, row.auto_apply_enabled) if row else (0, False)


async def set_auto_apply_enabled(
    merchant_id: str, product_id: str, action_type: str, enabled: bool, db: "AsyncSession"
) -> int:
    """The merchant's own toggle — called from the /products/{id}/autopilot-trust
    endpoint, never automatically. Enabling requires an already-earned streak
    (can't opt into trust that doesn't exist yet); disabling is always allowed,
    no threshold check, matching "trust is lost faster than it's earned."
    Returns the current streak so the caller can report it back.

    Raises ValueError if enabling is attempted below TRUST_STREAK_THRESHOLD —
    the caller (a real merchant action) should never hit this in the normal
    UI flow, where the toggle is only ever shown once eligible; it exists as
    a genuine guard against enabling trust that was never earned, not just a
    UI nicety."""
    from sqlalchemy import select
    from app.models.db_models import AutopilotTrustDB

    row = await db.scalar(
        select(AutopilotTrustDB)
        .where(AutopilotTrustDB.merchant_id == merchant_id)
        .where(AutopilotTrustDB.product_id == product_id)
        .where(AutopilotTrustDB.action_type == action_type)
    )
    streak = row.streak if row else 0
    if enabled and streak < TRUST_STREAK_THRESHOLD:
        raise ValueError(
            f"cannot enable auto-apply below the trust threshold "
            f"(streak={streak}, needs {TRUST_STREAK_THRESHOLD})"
        )
    if row:
        row.auto_apply_enabled = enabled
        row.updated_at = int(time.time() * 1000)
    else:
        # Only reachable for enabled=False on a never-earned pair — a no-op
        # worth persisting anyway so list_eligible_trust has one row per pair.
        db.add(AutopilotTrustDB(
            id=str(uuid.uuid4()), merchant_id=merchant_id, product_id=product_id,
            action_type=action_type, streak=0, auto_apply_enabled=enabled,
        ))
    await db.commit()
    logger.info(
        "[autopilot_trust] %s/%s/%s auto_apply_enabled -> %s (streak=%d)",
        merchant_id, product_id, action_type, enabled, streak,
    )
    return streak


async def list_eligible_trust(merchant_id: str, db: "AsyncSession") -> list[dict]:
    """Every (product, action_type) pair that has earned the threshold —
    what the terminal's Earned Trust panel shows, regardless of whether the
    merchant has already toggled it on. Includes the product name since the
    frontend has no other cheap way to resolve product_id -> a human label."""
    from sqlalchemy import select
    from app.models.db_models import AutopilotTrustDB, ProductDB

    rows = (await db.execute(
        select(AutopilotTrustDB, ProductDB.name)
        .join(ProductDB, ProductDB.id == AutopilotTrustDB.product_id)
        .where(AutopilotTrustDB.merchant_id == merchant_id)
        .where(AutopilotTrustDB.streak >= TRUST_STREAK_THRESHOLD)
    )).all()
    return [
        {
            "product_id": trust.product_id,
            "product_name": name,
            "action_type": trust.action_type,
            "streak": trust.streak,
            "auto_apply_enabled": trust.auto_apply_enabled,
        }
        for trust, name in rows
    ]


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
