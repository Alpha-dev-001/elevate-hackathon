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

    rows = await db.execute(
        select(OrderDB)
        .where(OrderDB.merchant_id == action.merchant_id)
        .where(OrderDB.promo_applied == action.promo_id)
    )
    orders = rows.scalars().all()
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

    if action.action_type == "price_rebalance":
        from app.services.autopilot_trust import update_trust_streak
        target_pid = (action.payload or {}).get("product_id", "")
        if target_pid:
            approved = behavior != "dismissed"
            outcome_negative = count == 0  # no attributed orders == negative outcome
            try:
                await update_trust_streak(
                    action.merchant_id, target_pid, "price_rebalance", db,
                    approved=approved, outcome_negative=outcome_negative,
                )
            except Exception as e:  # noqa: BLE001 — trust tracking must never block outcome observation
                logger.warning(
                    "[outcome_observer] trust streak update failed for %s: %s", action.id, e,
                )

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
