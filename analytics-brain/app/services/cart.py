"""
Cart — per-session, store-scoped, guest-first. Lives in Redis only: a cart is
ephemeral and replaceable, so it never needs Postgres. The one rule that matters
is the PRICE SNAPSHOT: the effective price is captured into the line the moment
an item is added, and later promo/price changes never mutate a cart already
built. That is correct commerce behavior and it's also what protects a customer
mid-checkout.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis, Keys, TTL
from app.models.db_models import ProductDB
from app.models.schemas import Cart, CartItem
from app.services import delta as delta_svc
from app.services.pricing import best_active_promo, effective_price, now_ms

__all__ = ["CartError", "get_cart", "add_item", "set_item", "clear_cart"]

logger = logging.getLogger(__name__)


class CartError(Exception):
    """A cart operation the customer should see a clear reason for
    (out of stock, product gone). Routers turn it into a 4xx, never a 500."""


def _empty(merchant_id: str, session_id: str) -> Cart:
    return Cart(
        session_id=session_id,
        merchant_id=merchant_id,
        items=[],
        subtotal=0.0,
        item_count=0,
        total=0.0,
        updated_at=now_ms(),
    )


def _recompute(cart: Cart) -> Cart:
    """Recompute the base totals from the lines. Leaves the recovery-discount
    fields alone — _apply_recovery owns those and always runs after this."""
    cart.subtotal = round(sum(i.line_total for i in cart.items), 2)
    cart.item_count = sum(i.qty for i in cart.items)
    cart.updated_at = now_ms()
    return cart


async def _apply_recovery(merchant_id: str, cart: Cart) -> Cart:
    """Overlay the merchant's active order-level recovery discount onto the cart.

    Recomputed on EVERY read from SystemState.recovery, so an expired or removed
    offer zeroes the discount out — a stale stored blob can never resurrect one.
    Product line snapshots are never touched: only the cart total moves, which is
    exactly the cart-recovery behavior (the browse grid stays at full price).
    Best-effort: a Redis blip leaves the cart at full price rather than 500-ing.
    """
    percent, label, expires_at = 0.0, None, None
    try:
        state = await delta_svc.load_state(merchant_id)
        rec = state.recovery if state else None
        if rec and cart.items and rec.percent > 0 and rec.expires_at > now_ms():
            percent, label, expires_at = rec.percent, rec.label, rec.expires_at
    except Exception as e:
        logger.warning(f"[cart] recovery overlay failed for {merchant_id}: {e}")

    cart.discount_percent = percent
    cart.discount_label = label
    cart.discount_expires_at = expires_at
    cart.discount_amount = round(cart.subtotal * percent / 100, 2) if percent else 0.0
    cart.total = round(cart.subtotal - cart.discount_amount, 2)
    return cart


async def get_cart(merchant_id: str, session_id: str) -> Cart:
    """Load the cart, or an empty one, with the live recovery discount overlaid.
    A corrupt blob degrades to empty rather than 500-ing the storefront."""
    cart = _empty(merchant_id, session_id)
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.cart(merchant_id, session_id))
        if raw:
            cart = Cart.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"[cart] read failed for {merchant_id}/{session_id}: {e}")
    return await _apply_recovery(merchant_id, cart)


async def _save(cart: Cart) -> None:
    redis = await get_redis()
    await redis.set(
        Keys.cart(cart.merchant_id, cart.session_id),
        cart.model_dump_json(),
        ex=TTL.CART,
    )
    # Keep the enumerable active-carts index in sync — every cart mutation
    # (add_item, set_item, including the qty<=0 removal path) goes through
    # this one function, so this is the single choke point to hook rather
    # than touching each call site separately.
    if cart.items:
        await redis.sadd(Keys.active_carts(cart.merchant_id), cart.session_id)
    else:
        await redis.srem(Keys.active_carts(cart.merchant_id), cart.session_id)


async def _live_product(db: AsyncSession, merchant_id: str, product_id: str) -> ProductDB:
    p = await db.get(ProductDB, product_id)
    if p is None or p.merchant_id != merchant_id or not p.is_active:
        raise CartError("That product isn't available.")
    return p


async def _snapshot_price(merchant_id: str, product: ProductDB) -> float:
    """Effective price right now — base minus the best active promo."""
    state = await delta_svc.load_state(merchant_id)
    promos = state.active_promos if state else {}
    promo = best_active_promo(product.id, promos)
    price, _, _ = effective_price(product.price, promo)
    return price


async def add_item(
    db: AsyncSession, merchant_id: str, session_id: str, product_id: str, qty: int
) -> Cart:
    """Add `qty` of a product. Keeps the original snapshot price if the line
    already exists (price protection). Caps at available stock."""
    if qty <= 0:
        raise CartError("Quantity must be at least 1.")

    product = await _live_product(db, merchant_id, product_id)
    cart = await get_cart(merchant_id, session_id)

    existing = next((i for i in cart.items if i.product_id == product_id), None)
    desired = (existing.qty if existing else 0) + qty
    if desired > product.stock:
        raise CartError(
            f"Only {product.stock} left in stock"
            if product.stock > 0
            else "That product is sold out."
        )

    if existing:
        existing.qty = desired
        existing.line_total = round(existing.unit_price * desired, 2)
    else:
        unit = await _snapshot_price(merchant_id, product)
        cart.items.append(
            CartItem(
                product_id=product.id,
                name=product.name,
                unit_price=unit,
                qty=desired,
                image_url=product.image_urls[0] if product.image_urls else None,
                line_total=round(unit * desired, 2),
            )
        )

    cart = _recompute(cart)
    cart = await _apply_recovery(merchant_id, cart)
    await _save(cart)
    return cart


async def set_item(
    db: AsyncSession, merchant_id: str, session_id: str, product_id: str, qty: int
) -> Cart:
    """Set the absolute quantity of a line. qty <= 0 removes it. Keeps the
    existing snapshot price."""
    cart = await get_cart(merchant_id, session_id)
    existing = next((i for i in cart.items if i.product_id == product_id), None)

    if qty <= 0:
        cart.items = [i for i in cart.items if i.product_id != product_id]
        cart = _recompute(cart)
        cart = await _apply_recovery(merchant_id, cart)
        await _save(cart)
        return cart

    product = await _live_product(db, merchant_id, product_id)
    if qty > product.stock:
        raise CartError(f"Only {product.stock} left in stock")

    if existing:
        existing.qty = qty
        existing.line_total = round(existing.unit_price * qty, 2)
    else:
        unit = await _snapshot_price(merchant_id, product)
        cart.items.append(
            CartItem(
                product_id=product.id,
                name=product.name,
                unit_price=unit,
                qty=qty,
                image_url=product.image_urls[0] if product.image_urls else None,
                line_total=round(unit * qty, 2),
            )
        )

    cart = _recompute(cart)
    cart = await _apply_recovery(merchant_id, cart)
    await _save(cart)
    return cart


async def clear_cart(merchant_id: str, session_id: str) -> Cart:
    try:
        redis = await get_redis()
        await redis.delete(Keys.cart(merchant_id, session_id))
        await redis.srem(Keys.active_carts(merchant_id), session_id)
    except Exception as e:
        logger.warning(f"[cart] clear failed for {merchant_id}/{session_id}: {e}")
    return _empty(merchant_id, session_id)
