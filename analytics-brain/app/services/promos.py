"""
Merchant promos. A promo is the merchant's pricing lever — and the first place
the interceptor's Layer 2/3 enforcement meets a real merchant action: the
discount is clamped to the ceiling and blocked if it would sell below cost.

Promos live durably in Postgres (PromoDB) and in SystemState.active_promos
(Redis) for hot-reload. Creating/removing one re-syncs SystemState and pushes
state_updated so connected storefronts re-price live.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import manager
from app.models.db_models import ProductDB, PromoDB
from app.models.schemas import (
    Promo,
    PromoCreate,
    Violation,
    WSMessage,
    WSEventType,
)
from app.services import delta as delta_svc
from app.services import interceptor
from app.services.profile import load_constraints
from app.services.pricing import now_ms

logger = logging.getLogger(__name__)


class PromoError(Exception):
    """A promo the interceptor hard-blocked (e.g. would sell below cost)."""


def _now() -> int:
    return int(time.time() * 1000)


async def _push_state(merchant_id: str) -> None:
    state = await delta_svc.load_state(merchant_id)
    if state is None:
        return
    state.version += 1
    state.last_updated = _now()
    await delta_svc.save_state(merchant_id, state)
    await manager.push_to_all(
        merchant_id,
        WSMessage(
            event=WSEventType.STATE_UPDATED,
            payload={"state": json.loads(state.model_dump_json())},
            merchant_id=merchant_id,
            timestamp=_now(),
        ),
    )


async def create_promo(
    db: AsyncSession, merchant_id: str, payload: PromoCreate
) -> tuple[Promo, list[Violation]]:
    """Create a promo after Layer 2/3 enforcement. Returns (promo, violations) —
    a `warning` clamps the discount and is shown to the merchant; a `blocked`
    raises PromoError."""
    product = await db.get(ProductDB, payload.product_id)
    if product is None or product.merchant_id != merchant_id or not product.is_active:
        raise PromoError("That product doesn't exist.")

    constraints = await load_constraints(db, merchant_id)
    final_discount, violations = interceptor.enforce_discount(
        cost_price=product.cost_price,
        base_price=product.price,
        discount_percent=payload.discount_percent,
        constraints=constraints,
    )
    if interceptor.blocked(violations):
        # Surface the block reason to the caller.
        msg = next((v.message for v in violations if v.severity == "blocked"), "Promo blocked.")
        raise PromoError(msg)

    promo = Promo(
        id=f"promo_{uuid.uuid4().hex[:10]}",
        product_id=product.id,
        discount_percent=final_discount,
        label=payload.label,
        expires_at=now_ms() + payload.duration_minutes * 60_000,
        triggered_by="merchant",
    )

    # Durable copy first (survives a Redis flush).
    db.add(
        PromoDB(
            id=promo.id,
            merchant_id=merchant_id,
            product_id=promo.product_id,
            discount_percent=promo.discount_percent,
            label=promo.label,
            expires_at=promo.expires_at,
            triggered_by=promo.triggered_by,
            is_active=True,
            created_at=_now(),
        )
    )
    await db.flush()

    # Hot-reload copy in SystemState.
    state = await delta_svc.load_state(merchant_id)
    if state is not None:
        state.active_promos[promo.id] = promo
        await delta_svc.save_state(merchant_id, state)
        await _push_state(merchant_id)

    return promo, violations


async def list_promos(db: AsyncSession, merchant_id: str) -> list[Promo]:
    """Active, non-expired promos from the durable store."""
    now = now_ms()
    rows = await db.scalars(
        select(PromoDB).where(
            PromoDB.merchant_id == merchant_id,
            PromoDB.is_active.is_(True),
            PromoDB.expires_at > now,
        )
    )
    return [
        Promo(
            id=r.id,
            product_id=r.product_id,
            discount_percent=r.discount_percent,
            label=r.label,
            expires_at=r.expires_at,
            triggered_by=r.triggered_by,  # type: ignore[arg-type]
        )
        for r in rows
    ]


async def delete_promo(db: AsyncSession, merchant_id: str, promo_id: str) -> None:
    row = await db.get(PromoDB, promo_id)
    if row is None or row.merchant_id != merchant_id:
        raise PromoError("Promo not found.")
    row.is_active = False
    await db.flush()

    state = await delta_svc.load_state(merchant_id)
    if state is not None and promo_id in state.active_promos:
        del state.active_promos[promo_id]
        await delta_svc.save_state(merchant_id, state)
        await _push_state(merchant_id)
