"""Outcome observer — the closing half of the cognitive loop.

After an agent action's promo resolves (expires or is dismissed), this queries
the orders attributed to it, summarizes the result, and writes a MemoryEntry the
next decision cycle will read. Scheduling uses an in-process asyncio timer; the
durable-queue production path is documented in the architecture diagram.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.models.schemas import MemoryEntry
from app.services.memory import write_memory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


def summarize_outcome(attributed_count: int, revenue: float) -> str:
    """Human-readable outcome line for a memory entry."""
    if attributed_count <= 0:
        return "no conversions"
    return f"{attributed_count} orders, ${revenue:.0f} revenue"


async def observe_outcome(
    action_id: str,
    db: "AsyncSession",
    redis: "Redis | None" = None,
    *,
    behavior: str | None = None,
) -> MemoryEntry | None:
    """Compute the action's outcome from attributed orders, write a memory entry."""
    from sqlalchemy import select
    from app.models.db_models import AgentActionDB, OrderDB

    action = await db.get(AgentActionDB, action_id)
    if action is None:
        logger.warning("[observer] action %s vanished before observation", action_id)
        return None

    # promo_applied is a ", "-joined list when discounts stack (flash_sale +
    # recovery), so an exact `== promo_id` match silently dropped stacked orders
    # (revenue landed but the loop mis-saw "no conversion"). Narrow in SQL with a
    # substring match, then confirm the exact token in Python. See attribution.py.
    from app.services.attribution import promo_ids_of
    rows = await db.execute(
        select(OrderDB)
        .where(OrderDB.merchant_id == action.merchant_id)
        .where(OrderDB.promo_applied.contains(action.promo_id))
    )
    orders = [o for o in rows.scalars().all() if action.promo_id in promo_ids_of(o.promo_applied)]
    count = len(orders)
    revenue = sum(float(o.total) for o in orders)

    entry = MemoryEntry(
        action_type=action.action_type,
        trigger=action.trigger_description or action.trigger,
        outcome=summarize_outcome(count, revenue),
        merchant_behavior=behavior or action.merchant_behavior or action.status,
    )
    await write_memory(action.merchant_id, entry, db, redis)
    logger.info("[observer] memory written for %s: %s → %s", action.merchant_id, action.action_type, entry.outcome)

    # PRICE_REBALANCE's graduated-autonomy trust streak (Task 11) has two
    # halves, split by how soon each is actually knowable:
    #
    # 1. A DISMISSAL is knowable instantly — reset it here, immediately,
    #    matching next_streak's documented "trust is lost faster than it's
    #    earned" rule. approved=False makes next_streak return 0 regardless
    #    of outcome_negative's value, so there's no real-purchase data to
    #    wait for in this branch.
    # 2. An EXECUTED move's real outcome is NOT knowable here. This
    #    function's `count` is computed from OrderDB.promo_applied ==
    #    action.promo_id — a direct price change never registers a
    #    Promo/RecoveryOffer, so that count would be structurally always 0
    #    for this action type (found in final whole-branch review). Even
    #    swapping the data source wouldn't help: schedule_observation fires
    #    this ~agent_action_duration_minutes (30 min default) after approval,
    #    long before rollup_daily_signals (a once-a-day job) has written any
    #    new product_price_history row to check. That half is evaluated on
    #    the daily pricing tick instead — see pricing_cycle.evaluate_trust_outcomes.
    if action.action_type == "price_rebalance" and entry.merchant_behavior == "dismissed":
        from app.services.autopilot_trust import update_trust_streak
        target_pid = (action.payload or {}).get("product_id", "")
        if target_pid:
            try:
                await update_trust_streak(
                    action.merchant_id, target_pid, "price_rebalance", db,
                    approved=False, outcome_negative=True,
                )
            except Exception as e:  # noqa: BLE001 — trust tracking must never block outcome observation
                # action_id (this function's own string parameter), not
                # action.id — a failed write can leave the session's
                # transaction poisoned, and re-touching an ORM attribute here
                # would trigger a lazy reload on that same broken session,
                # raising a SECOND exception from inside this handler.
                logger.warning(
                    "[outcome_observer] dismiss trust-reset failed for %s: %s", action_id, e,
                )
                # Recover the session — without this, every subsequent query
                # on this same `db` (including the caller's own ORM attribute
                # access right after this function returns) raises
                # PendingRollbackError instead of working normally. Safe here
                # specifically because write_memory (above) already committed
                # its own entry in a separate transaction — this only
                # discards the failed, uncommitted trust-streak write.
                await db.rollback()
                # rollback() unconditionally expires every object in the
                # session regardless of expire_on_commit (that setting only
                # governs commit) — `action` is the SAME identity-mapped
                # object the caller holds (dismiss_action's `row`), so a
                # plain attribute access on it right after this function
                # returns would trigger an implicit lazy-load, which async
                # SQLAlchemy does not support outside an explicit await
                # (raises MissingGreenlet). Refresh it back to a loaded state
                # now, on the properly awaited path, instead of leaving that
                # landmine for whatever the caller does next.
                await db.refresh(action)

    return entry


def schedule_observation(action_id: str, expires_at_ms: int, *, session_factory=None, redis=None) -> None:
    """Fire observe_outcome once the promo expires. In-process timer — fine for
    the short demo promos; a durable queue is the production path."""
    delay = max(0.0, (expires_at_ms - int(time.time() * 1000)) / 1000.0)

    async def _runner():
        await asyncio.sleep(delay)
        from app.core.database import get_session_factory
        factory = session_factory or get_session_factory()
        try:
            async with factory() as db:
                await observe_outcome(action_id, db, redis)
        except Exception as e:  # noqa: BLE001 — a failed observation must not crash the app
            logger.warning("[observer] scheduled observation failed for %s: %s", action_id, e)

    asyncio.create_task(_runner())
