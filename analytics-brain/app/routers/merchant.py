"""
Merchant operations — orders, promos, pricing constraints, and the Qwen catalog
review. All authenticated (session cookie). This is the terminal side: the
merchant tunes the levers and reviews Qwen's read on the catalog.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_merchant
from app.models.db_models import MerchantDB, OrderDB
from app.models.schemas import (
    Order,
    OrderStatusUpdate,
    Promo,
    PromoCreate,
    BusinessConstraints,
    ConstraintsUpdate,
    CatalogReview,
    AgentAction,
)
from app.services import promos as promos_svc
from app.services import orders as orders_svc
from app.services import catalog as catalog_svc
from app.services.orders import _to_order
from app.services.profile import load_constraints, save_constraints

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/merchant", tags=["merchant"])


# ── Qwen memory (sprint 3) ────────────────────────────────────────────────────

@router.get("/memory/{slug}")
async def get_qwen_memory(
    slug: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """The store's Qwen memory — what prior decisions taught the agent. Powers the
    terminal's "Remembers N previous decisions" badge."""
    if merchant.slug != slug:
        raise HTTPException(status_code=403, detail="Not your store")
    from app.services.memory import get_memory
    from app.core.redis import get_redis
    try:
        redis = await get_redis()
    except Exception:
        redis = None
    entries = await get_memory(merchant.id, db, redis)
    return {"entries": [e.model_dump(mode="json") for e in entries], "count": len(entries)}


# ── Orders ──────────────────────────────────────────────────────────────────────

@router.get("/orders", response_model=list[Order])
async def list_orders(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.scalars(
        select(OrderDB)
        .where(OrderDB.merchant_id == merchant.id)
        .order_by(desc(OrderDB.created_at))
    )
    return [_to_order(r) for r in rows]


@router.patch("/orders/{order_id}", response_model=Order)
async def update_order_status(
    order_id: str,
    body: OrderStatusUpdate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await orders_svc.update_status(db, merchant.id, order_id, body)
    except orders_svc.OrderError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Promos ──────────────────────────────────────────────────────────────────────

@router.get("/promos", response_model=list[Promo])
async def list_promos(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    return await promos_svc.list_promos(db, merchant.id)


@router.post("/promos")
async def create_promo(
    body: PromoCreate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a promo. The interceptor clamps an over-ceiling discount (returned
    in `violations`) and blocks one that would sell below cost (409)."""
    try:
        promo, violations = await promos_svc.create_promo(db, merchant.id, body)
    except promos_svc.PromoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "promo": promo.model_dump(),
        "violations": [v.model_dump() for v in violations],
    }


@router.delete("/promos/{promo_id}", status_code=204)
async def delete_promo(
    promo_id: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        await promos_svc.delete_promo(db, merchant.id, promo_id)
    except promos_svc.PromoError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Pricing constraints (interceptor Layer 2 levers) ────────────────────────────

@router.get("/constraints", response_model=BusinessConstraints)
async def get_constraints(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    return await load_constraints(db, merchant.id)


@router.put("/constraints", response_model=BusinessConstraints)
async def update_constraints(
    body: ConstraintsUpdate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Merge provided fields onto current constraints, persist, return the result."""
    current = await load_constraints(db, merchant.id)
    merged = current.model_copy(
        update={k: v for k, v in body.model_dump().items() if v is not None}
    )
    await save_constraints(db, merchant.id, merged)
    return merged


# ── Qwen catalog review (observe-only) ──────────────────────────────────────────

@router.get("/catalog-review", response_model=CatalogReview | None)
async def get_catalog_review(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Cached review, or null if it's never been run."""
    return await catalog_svc.get_cached_review(merchant.id)


@router.post("/catalog-review", response_model=CatalogReview)
async def run_catalog_review(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Run (or re-run) the qwen-max catalog pricing review."""
    return await catalog_svc.review_catalog(db, merchant.id)


# ── Proactive store review (acts, unlike catalog-review above) ──────────────────

@router.post("/store-review", response_model=AgentAction | None)
async def run_store_review_now(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """On-demand proactive review — the same cycle the background loop runs
    hourly, fired immediately. Scans view-vs-order performance and, if a
    product stands out, runs it through the real decision cycle (same
    tool-calling path as a velocity spike or cart-abandon surge). Returns
    null when the catalog looks healthy or a decision is already pending —
    both are correct, quiet outcomes, not errors.
    """
    from app.core.redis import get_redis
    from app.services.store_review import run_store_review
    redis = await get_redis()
    return await run_store_review(merchant.id, db, redis)
