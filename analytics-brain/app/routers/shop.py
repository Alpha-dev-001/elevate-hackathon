"""
Customer-facing commerce — public, no auth, slug-scoped. Cart lives in Redis
keyed by a guest session_id the frontend generates; checkout turns it into a
durable order. Customers never see Elevate chrome or any merchant internals.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import MerchantDB
from app.models.schemas import (
    Cart,
    CartMutation,
    CheckoutRequest,
    Order,
)
from app.services import cart as cart_svc
from app.services import orders as orders_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/store/{slug}", tags=["shop"])


async def _live_merchant_id(slug: str, db: AsyncSession) -> str:
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if merchant is None or not merchant.is_live:
        raise HTTPException(status_code=404, detail="Store not found")
    return merchant.id


# ── Cart ──────────────────────────────────────────────────────────────────────

@router.get("/cart", response_model=Cart)
async def get_cart(
    slug: str,
    session_id: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
):
    merchant_id = await _live_merchant_id(slug, db)
    return await cart_svc.get_cart(merchant_id, session_id)


@router.post("/cart/items", response_model=Cart)
async def add_to_cart(slug: str, body: CartMutation, db: AsyncSession = Depends(get_db)):
    merchant_id = await _live_merchant_id(slug, db)
    try:
        return await cart_svc.add_item(db, merchant_id, body.session_id, body.product_id, body.qty)
    except cart_svc.CartError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/cart/items", response_model=Cart)
async def set_cart_item(slug: str, body: CartMutation, db: AsyncSession = Depends(get_db)):
    """Set the absolute quantity of a line. qty <= 0 removes it."""
    merchant_id = await _live_merchant_id(slug, db)
    try:
        return await cart_svc.set_item(db, merchant_id, body.session_id, body.product_id, body.qty)
    except cart_svc.CartError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/cart", response_model=Cart)
async def clear_cart(
    slug: str,
    session_id: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
):
    merchant_id = await _live_merchant_id(slug, db)
    return await cart_svc.clear_cart(merchant_id, session_id)


# ── Checkout + order lookup ─────────────────────────────────────────────────────

@router.post("/checkout", response_model=Order)
async def checkout(slug: str, body: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    merchant_id = await _live_merchant_id(slug, db)
    try:
        return await orders_svc.checkout(db, merchant_id, body.session_id, body.customer)
    except orders_svc.OrderError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/order/{order_id}", response_model=Order)
async def get_order(
    slug: str,
    order_id: str,
    email: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
):
    merchant_id = await _live_merchant_id(slug, db)
    try:
        return await orders_svc.get_order(db, merchant_id, order_id, email)
    except orders_svc.OrderError as e:
        raise HTTPException(status_code=404, detail=str(e))
