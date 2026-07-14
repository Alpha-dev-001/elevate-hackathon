"""
Daily price-history rollup — turns yesterday's capped, TTL'd Redis behavior
events (Keys.events, 500-item cap, ~25h TTL — see TTL.EVENTS) into one durable
Postgres row per product per day. This is what makes "this product's history"
mean something that survives past an hour; without it, dynamic pricing would
only ever see the live 30-second anomaly window behavior_tracker reads.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.core.redis import Keys

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _yesterday_utc() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def count_signals_for_product(events: list[dict], product_id: str) -> dict:
    """Pure aggregation: views/cart_adds for one product out of a raw
    event-dict list already pulled from Redis. No I/O — easy to test.

    Purchases are NOT counted here — Keys.events structurally never contains
    a purchase signal (checkout creates an OrderDB row but never fires a
    behavior event; the only two push_event call sites in the backend,
    behavior.py:53 and behavior.py:150, never send event_type="purchase").
    OrderDB is the durable, authoritative source for purchases (same
    precedent store_review.py's find_underperformer already established for
    "did this product convert" — see purchase_counts_for_date below), so
    purchase counting is a separate, DB-backed function, not part of this
    pure event-list aggregation.

    Note: "add_to_cart" is the real wire-format string the event pipeline
    writes (behavior.py:33, :53-58) — NOT "cart_add", which is a different
    pipeline's internal EventType enum value.
    """
    views = cart_adds = 0
    for e in events:
        if e.get("product_id") != product_id:
            continue
        et = e.get("event_type")
        if et == "view":
            views += 1
        elif et == "add_to_cart":
            cart_adds += 1
    return {"views": views, "cart_adds": cart_adds}


async def purchase_counts_for_date(
    db: "AsyncSession", merchant_id: str, date_str: str
) -> dict[str, int]:
    """Sum quantities purchased per product from real OrderDB rows created
    on date_str (UTC). OrderDB.items is a JSON list of {"product_id", "qty",
    ...} dicts (OrderItem shape, schemas.py:754-759) — same flattening
    pattern store_review.py's extract_ordered_product_ids already uses for
    orders, just counting quantities instead of collecting a set of ids."""
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta
    from app.models.db_models import OrderDB

    day_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    start_ms = int(day_start.timestamp() * 1000)
    end_ms = int(day_end.timestamp() * 1000)

    orders = (
        await db.execute(
            select(OrderDB)
            .where(OrderDB.merchant_id == merchant_id)
            .where(OrderDB.created_at >= start_ms)
            .where(OrderDB.created_at < end_ms)
        )
    ).scalars().all()

    counts: dict[str, int] = {}
    for order in orders:
        for item in order.items or []:
            if not isinstance(item, dict):
                continue
            pid = item.get("product_id")
            qty = item.get("qty")
            if pid and isinstance(qty, int):
                counts[pid] = counts.get(pid, 0) + qty
    return counts


async def rollup_daily_signals(
    db: "AsyncSession", redis: "Redis", *, target_date: str | None = None
) -> int:
    """Write one product_price_history row per active product across every
    live merchant, for target_date (defaults to yesterday UTC). Returns the
    number of rows written/updated. Per-product try/except — one bad product
    must never skip the rest, same discipline as store_review.py's tick.
    Idempotent: re-running for the same date overwrites that date's row
    rather than duplicating it (safe if the job is ever run twice)."""
    from sqlalchemy import select
    from app.models.db_models import MerchantDB, ProductDB, ProductPriceHistoryDB

    date_str = target_date or _yesterday_utc()
    written = 0

    merchants = (
        await db.execute(select(MerchantDB).where(MerchantDB.is_live == True))
    ).scalars().all()

    for merchant in merchants:
        try:
            raw_events = await redis.lrange(Keys.events(merchant.id), 0, -1)
            events = [json.loads(e) for e in raw_events]
        except Exception as e:  # noqa: BLE001 — one merchant's Redis blip must not skip the rest
            logger.warning("[pricing_signals] event read failed for %s: %s", merchant.id, e)
            continue

        try:
            purchase_counts = await purchase_counts_for_date(db, merchant.id, date_str)
        except Exception as e:  # noqa: BLE001 — one merchant's DB blip must not skip the rest
            logger.warning("[pricing_signals] purchase count failed for %s: %s", merchant.id, e)
            purchase_counts = {}

        products = (
            await db.execute(
                select(ProductDB)
                .where(ProductDB.merchant_id == merchant.id)
                .where(ProductDB.is_active == True)
            )
        ).scalars().all()

        for product in products:
            try:
                counts = count_signals_for_product(events, product.id)
                purchases = purchase_counts.get(product.id, 0)
                existing = await db.scalar(
                    select(ProductPriceHistoryDB)
                    .where(ProductPriceHistoryDB.product_id == product.id)
                    .where(ProductPriceHistoryDB.date == date_str)
                )
                if existing:
                    existing.views = counts["views"]
                    existing.cart_adds = counts["cart_adds"]
                    existing.purchases = purchases
                    existing.price_active = product.price
                else:
                    db.add(ProductPriceHistoryDB(
                        id=str(uuid.uuid4()),
                        product_id=product.id,
                        date=date_str,
                        views=counts["views"],
                        cart_adds=counts["cart_adds"],
                        purchases=purchases,
                        price_active=product.price,
                    ))
                written += 1
            except Exception as e:  # noqa: BLE001 — one product's failure must not skip the rest
                logger.warning(
                    "[pricing_signals] rollup failed for product %s: %s", product.id, e
                )

    await db.commit()
    return written
