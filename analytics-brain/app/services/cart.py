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
from app.models.schemas import Cart, CartItem, RecoveryOffer
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


async def set_dwell_offer(merchant_id: str, session_id: str, offer: RecoveryOffer) -> None:
    """Persist a cart_dwell_nudge discount scoped to exactly this session.
    Redis TTL matches the offer's own expiry so a stale key can never
    outlive the discount it represents — no separate cleanup needed."""
    redis = await get_redis()
    ttl_seconds = max(60, (offer.expires_at - now_ms()) // 1000)
    await redis.set(
        Keys.dwell_offer(merchant_id, session_id),
        offer.model_dump_json(),
        ex=ttl_seconds,
    )


async def _get_dwell_offer(merchant_id: str, session_id: str) -> RecoveryOffer | None:
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.dwell_offer(merchant_id, session_id))
        if raw:
            return RecoveryOffer.model_validate_json(raw)
    except Exception as e:  # noqa: BLE001 — a Redis blip must not break checkout
        logger.warning(f"[cart] dwell offer read failed for {merchant_id}/{session_id}: {e}")
    return None


async def get_effective_discount(merchant_id: str, session_id: str) -> RecoveryOffer | None:
    """The discount that actually applies to THIS session's order right now:
    the merchant-wide recovery_offer (applies to every session) or this
    session's own cart_dwell_nudge offer (applies to no one else), whichever
    is larger. Both are re-checked for expiry here, never trusted from a
    stale read — a merchant's offer expiring takes effect on the very next
    call. Single source of truth for both the cart display (_apply_recovery
    below) and the checkout math (orders.checkout) — they must never compute
    this independently or they can drift apart, which was the original bug
    (checkout re-derived it straight from SystemState.recovery instead of
    reading what the cart had already computed)."""
    candidates: list[RecoveryOffer] = []

    state = await delta_svc.load_state(merchant_id)
    if state and state.recovery and state.recovery.percent > 0 and state.recovery.expires_at > now_ms():
        candidates.append(state.recovery)

    dwell = await _get_dwell_offer(merchant_id, session_id)
    if dwell and dwell.percent > 0 and dwell.expires_at > now_ms():
        candidates.append(dwell)

    if not candidates:
        return None
    return max(candidates, key=lambda o: o.percent)


async def _apply_recovery(merchant_id: str, cart: Cart) -> Cart:
    """Overlay whichever discount actually applies to THIS cart's session
    right now (see get_effective_discount) onto the cart total. Recomputed
    on EVERY read, so an expired or dismissed offer zeroes the discount out
    — a stale stored blob can never resurrect one. Product line snapshots
    are never touched: only the cart total moves. Best-effort: a Redis blip
    leaves the cart at full price rather than 500-ing.
    """
    offer: RecoveryOffer | None = None
    try:
        if cart.items:
            offer = await get_effective_discount(merchant_id, cart.session_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[cart] recovery overlay failed for {merchant_id}: {e}")

    cart.discount_percent = offer.percent if offer else 0.0
    cart.discount_label = offer.label if offer else None
    cart.discount_expires_at = offer.expires_at if offer else None
    cart.discount_promo_id = offer.promo_id if offer else None
    cart.discount_amount = round(cart.subtotal * cart.discount_percent / 100, 2) if offer else 0.0
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
