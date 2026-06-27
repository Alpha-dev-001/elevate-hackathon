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

    # Build promo_id → orders map
    promo_to_orders: dict[str, list[OrderDB]] = {}
    for order in orders:
        if order.promo_applied:
            promo_to_orders.setdefault(order.promo_applied, []).append(order)

    action_rows = []
    elevate_attributed_gmv = 0.0

    for action in actions:
        attributed = promo_to_orders.get(action.promo_id, [])
        attributed_gmv = sum(float(o.total) for o in attributed)
        fee = round(attributed_gmv * ELEVATE_FEE_RATE, 2)
        elevate_attributed_gmv += attributed_gmv

        action_rows.append({
            "promo_id": action.promo_id,
            "action_type": action.action_type,
            "title": action.title,
            "trigger": action.trigger,
            "estimated_gmv": action.estimated_gmv,
            "executed_at": action.executed_at,
            "attributed_orders": len(attributed),
            "attributed_gmv": round(attributed_gmv, 2),
            "fee": fee,
        })

    return {
        "store_name": merchant.store_name,
        "total_gmv": round(total_gmv, 2),
        "elevate_attributed_gmv": round(elevate_attributed_gmv, 2),
        "elevate_fee": round(elevate_attributed_gmv * ELEVATE_FEE_RATE, 2),
        "actions": action_rows,
    }
