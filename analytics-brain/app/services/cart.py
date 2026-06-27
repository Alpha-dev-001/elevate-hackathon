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
        updated_at=now_ms(),
    )


def _recompute(cart: Cart) -> Cart:
    cart.subtotal = round(sum(i.line_total for i in cart.items), 2)
    cart.item_count = sum(i.qty for i in cart.items)
    cart.updated_at = now_ms()
    return cart


async def get_cart(merchant_id: str, session_id: str) -> Cart:
    """Load the cart, or an empty one. A corrupt blob degrades to empty rather
    than 500-ing the storefront."""
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.cart(merchant_id, session_id))
        if raw:
            return Cart.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"[cart] read failed for {merchant_id}/{session_id}: {e}")
    return _empty(merchant_id, session_id)


async def _save(cart: Cart) -> None:
    redis = await get_redis()
    await redis.set(
        Keys.cart(cart.merchant_id, cart.session_id),
        cart.model_dump_json(),
        ex=TTL.CART,
    )


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
    await _save(cart)
    return cart


async def clear_cart(merchant_id: str, session_id: str) -> Cart:
    try:
        redis = await get_redis()
        await redis.delete(Keys.cart(merchant_id, session_id))
    except Exception as e:
        logger.warning(f"[cart] clear failed for {merchant_id}/{session_id}: {e}")
    return _empty(merchant_id, session_id)
