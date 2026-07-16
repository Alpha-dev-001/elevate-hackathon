"""
Checkout + orders. Cart (Redis, snapshot prices) -> Order (Postgres, durable).

The one thing that must be right under concurrency is stock: two customers
buying the last unit cannot both succeed. We decrement with a conditional
UPDATE (`stock = stock - qty WHERE stock >= qty`) inside the request
transaction — Postgres re-checks the predicate after row-locking, so an oversell
is impossible. Any shortfall aborts the WHOLE order (rollback), never a partial
decrement. Snapshot prices from the cart are honored verbatim.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis, Keys
from app.core.ws_manager import manager
from app.models.db_models import ProductDB, OrderDB
from app.models.schemas import (
    Order,
    OrderItem,
    OrderStatus,
    OrderCustomer,
    OrderStatusUpdate,
    WSMessage,
    WSEventType,
)
from app.services import cart as cart_svc
from app.services import delta as delta_svc
from app.services.pricing import best_active_promo
from app.services.products import products_state_map

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """A checkout problem the customer should see plainly (empty cart, stock
    shortfall). Routes map it to a 409, never a 500."""


def _now() -> int:
    return int(time.time() * 1000)


def _to_order(row: OrderDB) -> Order:
    return Order(
        id=row.id,
        merchant_id=row.merchant_id,
        session_id=row.session_id,
        items=[OrderItem.model_validate(i) for i in row.items],
        subtotal=row.subtotal,
        total=row.total,
        status=OrderStatus(row.status),
        customer_name=row.customer_name,
        customer_email=row.customer_email,
        promo_applied=row.promo_applied,
        created_at=row.created_at,
    )


async def _sync_state_after_stock_change(db: AsyncSession, merchant_id: str) -> None:
    """Stock changed -> refresh SystemState.products and push to the storefront
    so availability flips live. Best-effort: the order is already committed, so a
    Redis blip here can't lose it."""
    try:
        state = await delta_svc.load_state(merchant_id)
        if state is None:
            return
        state.products = await products_state_map(db, merchant_id)
        state.version += 1
        state.last_updated = _now()
        await delta_svc.save_state(merchant_id, state)
        # Push to BOTH surfaces: the storefront refreshes availability/prices, and
        # the merchant terminal refetches attribution so revenue ticks up live on
        # checkout instead of staying $0 until a manual refresh.
        await manager.push_to_all(
            merchant_id,
            WSMessage(
                event=WSEventType.STATE_UPDATED,
                payload={"state": json.loads(state.model_dump_json())},
                merchant_id=merchant_id,
                timestamp=_now(),
            ),
        )
    except Exception as e:
        logger.warning(f"[orders] post-checkout state sync failed for {merchant_id}: {e}")


async def checkout(
    db: AsyncSession,
    merchant_id: str,
    session_id: str,
    customer: OrderCustomer,
) -> Order:
    cart = await cart_svc.get_cart(merchant_id, session_id)
    if not cart.items:
        raise OrderError("Your cart is empty.")

    # Which active promos touch the cart — recorded for the merchant's records.
    state = await delta_svc.load_state(merchant_id)
    active_promos = state.active_promos if state else {}

    order_items: list[OrderItem] = []
    # Tag the order with the promo *id* (not its label): attribution in
    # dashboard.py and outcome_observer.py matches OrderDB.promo_applied against
    # AgentActionDB.promo_id. Storing the label here silently broke that match —
    # every AI-driven sale read back as "no conversions", poisoning the memory loop.
    promo_ids: list[str] = []

    for item in cart.items:
        result = await db.execute(
            update(ProductDB)
            .where(
                ProductDB.id == item.product_id,
                ProductDB.merchant_id == merchant_id,
                ProductDB.is_active.is_(True),
                ProductDB.stock >= item.qty,
            )
            .values(stock=ProductDB.stock - item.qty)
        )
        if result.rowcount == 0:
            # Re-read to tell the customer exactly what changed under them.
            p = await db.get(ProductDB, item.product_id)
            available = p.stock if (p and p.is_active) else 0
            raise OrderError(
                f"{item.name}: only {available} left in stock — please update your cart."
            )

        order_items.append(
            OrderItem(
                product_id=item.product_id,
                name=item.name,
                unit_price=item.unit_price,
                qty=item.qty,
                line_total=item.line_total,
            )
        )
        promo = best_active_promo(item.product_id, active_promos)
        if promo:
            promo_ids.append(promo.id)

    subtotal = round(sum(i.line_total for i in order_items), 2)

    # Order-level discount (recovery_offer store-wide, or cart_dwell_nudge
    # scoped to this exact session) — cart.py's get_effective_discount is the
    # single source of truth for both the cart's on-screen total and this
    # checkout math, so they can never drift apart. cart was already fetched
    # above with the live discount overlaid. It drops the order total and,
    # crucially, attributes the sale to that action so the dashboard
    # money-shot reads the AI-driven revenue instead of $0.
    discount_amount = round(subtotal * cart.discount_percent / 100, 2) if cart.discount_percent > 0 else 0.0
    if cart.discount_promo_id:
        promo_ids.append(cart.discount_promo_id)
    total = round(subtotal - discount_amount, 2)

    order = OrderDB(
        id=f"ord_{uuid.uuid4().hex[:12]}",
        merchant_id=merchant_id,
        session_id=session_id,
        items=[i.model_dump() for i in order_items],
        subtotal=subtotal,
        total=total,  # subtotal minus any recovery discount; no shipping/tax in the demo
        status=OrderStatus.PAID.value,  # payment is simulated as successful
        customer_name=customer.name,
        customer_email=customer.email,
        promo_applied=", ".join(sorted(set(promo_ids))) or None,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(order)

    # Commit BEFORE broadcasting so we never push state for an order that didn't
    # land. expire_on_commit=False keeps `order` usable afterward.
    await db.commit()

    await cart_svc.clear_cart(merchant_id, session_id)
    await _sync_state_after_stock_change(db, merchant_id)

    logger.info(f"[orders] {order.id} placed for {merchant_id} (${subtotal})")
    return _to_order(order)


async def get_order(db: AsyncSession, merchant_id: str, order_id: str, email: str) -> Order:
    """Customer order lookup — id + matching email (guest-safe, no accounts)."""
    row = await db.get(OrderDB, order_id)
    if row is None or row.merchant_id != merchant_id:
        raise OrderError("Order not found.")
    if row.customer_email.lower() != email.strip().lower():
        raise OrderError("Order not found.")
    return _to_order(row)


async def update_status(
    db: AsyncSession, merchant_id: str, order_id: str, update_req: OrderStatusUpdate
) -> Order:
    row = await db.get(OrderDB, order_id)
    if row is None or row.merchant_id != merchant_id:
        raise OrderError("Order not found.")
    row.status = update_req.status.value
    row.updated_at = _now()
    await db.flush()
    return _to_order(row)
