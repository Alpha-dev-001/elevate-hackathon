"""
Attribution dashboard — shows what the AI drove and what the fee would be.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import AgentActionDB, MerchantDB, OrderDB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

ELEVATE_FEE_RATE = 0.10  # 10% of attributed GMV


@router.get("/{slug}")
async def get_dashboard(slug: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    # All orders for this store
    all_orders_result = await db.scalars(
        select(OrderDB).where(OrderDB.merchant_id == merchant.id)
    )
    orders = list(all_orders_result)
    total_gmv = sum(float(o.total) for o in orders)

    # Executed actions with their attributed orders
    executed_result = await db.scalars(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant.id)
        .where(AgentActionDB.status == "executed")
        .order_by(AgentActionDB.executed_at.desc())
    )
    actions = list(executed_result)

    # Attribute orders to actions. An order can carry two stacked promos
    # (product flash_sale + order-level recovery), so promo_applied is a
    # ", "-joined list — split it so a stacked order is credited to every action
    # that drove it, and count it once in the store total. See attribution.py.
    from app.services.attribution import attribute_orders, total_attributed_gmv
    attributed_map = attribute_orders(orders, [a.promo_id for a in actions])

    action_rows = []
    for action in actions:
        attributed = attributed_map.get(action.promo_id, [])
        attributed_gmv = round(sum(float(o.total) for o in attributed), 2)

        action_rows.append({
            "promo_id": action.promo_id,
            "action_type": action.action_type,
            "title": action.title,
            "trigger": action.trigger,
            "estimated_gmv": action.estimated_gmv,
            "executed_at": action.executed_at,
            "attributed_orders": len(attributed),
            "attributed_gmv": attributed_gmv,
            "fee": round(attributed_gmv * ELEVATE_FEE_RATE, 2),
        })

    # Distinct orders only — a stacked order matched by two actions counts once.
    elevate_attributed_gmv = total_attributed_gmv(attributed_map)

    # Memory count — how many decisions Qwen has learned from for this store
    from app.services.memory import get_memory
    from app.core.redis import get_redis
    try:
        redis = await get_redis()
        entries = await get_memory(merchant.id, db, redis)
        memory_count = len(entries)
    except Exception:
        memory_count = 0

    return {
        "store_name": merchant.store_name,
        "total_gmv": round(total_gmv, 2),
        "elevate_attributed_gmv": round(elevate_attributed_gmv, 2),
        "elevate_fee": round(elevate_attributed_gmv * ELEVATE_FEE_RATE, 2),
        "actions": action_rows,
        "memory_count": memory_count,
    }


@router.get("/{slug}/usage")
async def get_usage(slug: str, db: AsyncSession = Depends(get_db)):
    """Token usage and estimated cost for all Qwen calls made for this store."""
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    from app.services.brand import get_usage_summary
    summary = await get_usage_summary(merchant.id)
    return {"store_name": merchant.store_name, **summary}
