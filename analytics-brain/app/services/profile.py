"""
Business profile / interceptor constraints — durable in Postgres, cached in
Redis. The constraints are the levers behind the interceptor's Layer 2 (margin
floor, discount ceiling, per-product minimum price).

"If it needs to exist tomorrow it goes to Postgres first, then cached in Redis."
The legacy Redis-only profile (written at publish in Sprint 1) is still read as
a fallback so already-live stores keep working.
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis, Keys
from app.models.db_models import BusinessProfileDB
from app.models.schemas import BusinessConstraints, BusinessProfile
from app.services.products import load_products, db_to_product

logger = logging.getLogger(__name__)


def _now() -> int:
    return int(time.time() * 1000)


async def load_constraints(db: AsyncSession, merchant_id: str) -> BusinessConstraints:
    """Redis cache → Postgres → sane defaults. Never raises — a missing profile
    yields defaults so the interceptor always has floors to enforce."""
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.profile(merchant_id))
        if raw:
            doc = json.loads(raw)
            # Stored shape may be a full BusinessProfile (Sprint 1) or just constraints.
            constraints = doc.get("constraints", doc)
            return BusinessConstraints.model_validate(constraints)
    except Exception as e:
        logger.warning(f"[profile] Redis constraints read failed for {merchant_id}: {e}")

    row = await db.get(BusinessProfileDB, merchant_id)
    if row is not None:
        try:
            return BusinessConstraints.model_validate(row.constraints)
        except ValueError as e:
            logger.error(f"[profile] corrupt constraints for {merchant_id}: {e}")

    return BusinessConstraints()


async def save_constraints(
    db: AsyncSession, merchant_id: str, constraints: BusinessConstraints
) -> None:
    """Persist to Postgres (source of truth), then cache in Redis."""
    row = await db.get(BusinessProfileDB, merchant_id)
    if row is None:
        db.add(
            BusinessProfileDB(
                merchant_id=merchant_id,
                constraints=constraints.model_dump(),
                updated_at=_now(),
            )
        )
    else:
        row.constraints = constraints.model_dump()
        row.updated_at = _now()
    await db.flush()

    try:
        redis = await get_redis()
        await redis.set(Keys.profile(merchant_id), constraints.model_dump_json())
    except Exception as e:
        logger.warning(f"[profile] Redis constraints cache failed for {merchant_id}: {e}")


async def load_business_profile(db: AsyncSession, merchant_id: str) -> BusinessProfile:
    """Constraints + the merchant's live products (with cost_price) — the shape
    the interceptor consumes when validating price/discount actions."""
    constraints = await load_constraints(db, merchant_id)
    products = [db_to_product(r) for r in await load_products(db, merchant_id)]
    return BusinessProfile(
        merchant_id=merchant_id,
        store_name="",
        constraints=constraints,
        products=products,
    )
