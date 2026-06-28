"""
Agent action management — pending, approve, dismiss.
Approve executes the payload and broadcasts the store update via WebSocket.
"""
from __future__ import annotations

import time
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import AgentActionDB, MerchantDB
from app.models.schemas import AgentAction, AgentActionStatus, AgentActionType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


def _to_schema(row: AgentActionDB) -> AgentAction:
    return AgentAction(
        id=row.id,
        merchant_id=row.merchant_id,
        promo_id=row.promo_id,
        action_type=AgentActionType(row.action_type),
        trigger=row.trigger,
        title=row.title,
        description=row.description,
        estimated_gmv=row.estimated_gmv,
        estimated_confidence=row.estimated_confidence,
        payload=row.payload,
        brand_check=row.brand_check,
        status=AgentActionStatus(row.status),
        created_at=row.created_at,
        approved_at=row.approved_at,
        executed_at=row.executed_at,
    )


@router.get("/actions/{slug}/pending")
async def get_pending_actions(slug: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    result = await db.execute(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant.id)
        .where(AgentActionDB.status == "pending")
        .order_by(AgentActionDB.created_at.desc())
    )
    rows = result.scalars().all()
    return {"actions": [_to_schema(r).model_dump() for r in rows]}


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {row.status}")

    now = int(time.time() * 1000)
    row.status = "approved"
    row.approved_at = now
    row.merchant_behavior = "approved"

    # Execute payload — apply flash_sale as a promo, layout_morph updates state, etc.
    await _execute_payload(row, db)

    row.status = "executed"
    row.executed_at = int(time.time() * 1000)
    await db.commit()

    # Broadcast store update to all WS connections
    await _broadcast_state_update(row.merchant_id)

    # Schedule the outcome observation for when this action's promo expires —
    # closes the cognitive loop (action → outcome → memory).
    try:
        from app.services.outcome_observer import schedule_observation
        from app.core.redis import get_redis
        state = await _load_state_promo_expiry(row, db)
        if state is not None:
            schedule_observation(row.id, state, redis=await get_redis())
    except Exception as e:  # noqa: BLE001 — observation scheduling must never fail the approve
        import logging
        logging.getLogger(__name__).warning("[agent] could not schedule observation for %s: %s", row.id, e)

    return {"action": _to_schema(row).model_dump()}


async def _load_state_promo_expiry(row: AgentActionDB, db: AsyncSession) -> int | None:
    """The expiry ms of this action's promo, if it created one. Falls back to a
    short window so the observer still fires for the demo."""
    import time as _t
    payload = row.payload or {}
    minutes = payload.get("duration_minutes") or payload.get("flash_sale", {}).get("duration_minutes")
    try:
        minutes = int(minutes) if minutes else 30
    except (TypeError, ValueError):
        minutes = 30
    return int(_t.time() * 1000) + minutes * 60 * 1000


@router.post("/actions/{action_id}/dismiss")
async def dismiss_action(action_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    row.status = "dismissed"
    row.merchant_behavior = "dismissed"
    await db.commit()

    # A dismissed action still teaches Qwen — observe it now (no promo to wait on).
    try:
        from app.services.outcome_observer import observe_outcome
        from app.core.redis import get_redis
        await observe_outcome(row.id, db, await get_redis(), behavior="dismissed")
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("[agent] dismiss observation failed for %s: %s", row.id, e)

    return {"action": _to_schema(row).model_dump()}


async def _execute_payload(row: AgentActionDB, db: AsyncSession) -> None:
    """Apply the action's payload to the live store state."""
    from app.services import delta as delta_svc
    from app.models.schemas import Promo

    payload = row.payload or {}

    if row.action_type == "flash_sale":
        discount = float(payload.get("discount_percent", 15))
        duration = int(payload.get("duration_minutes", 30))
        expires_at = int(time.time() * 1000) + duration * 60 * 1000

        state = await delta_svc.load_state(row.merchant_id)
        if not state:
            logger.warning(
                "[agent] flash_sale: state not found for merchant %s — promo not applied",
                row.merchant_id,
            )
        else:
            promo = Promo(
                id=row.promo_id,
                product_id=list(state.products.keys())[0] if state.products else "all",
                discount_percent=discount,
                label=f"Flash Sale — {int(discount)}% off",
                expires_at=expires_at,
                triggered_by="auto",
            )
            state.active_promos[row.promo_id] = promo
            await delta_svc.save_state(row.merchant_id, state)

    elif row.action_type == "layout_morph":
        state = await delta_svc.load_state(row.merchant_id)
        if state:
            new_grid = payload.get("new_grid")
            if new_grid:
                from app.models.schemas import LayoutVariant
                try:
                    state.layout_config.layout_variant = LayoutVariant(new_grid)
                except ValueError:
                    pass
            await delta_svc.save_state(row.merchant_id, state)

    # recovery_offer, scarcity_price, copy_rewrite — log for now, extend post-hackathon
    else:
        logger.info(f"[agent] action type {row.action_type} logged but not auto-applied")


async def _broadcast_state_update(merchant_id: str) -> None:
    from app.core.ws_manager import manager
    from app.models.schemas import WSMessage, WSEventType
    from app.services import delta as delta_svc

    state = await delta_svc.load_state(merchant_id)
    if not state:
        return

    import json
    msg = WSMessage(
        event=WSEventType.STATE_UPDATED,
        payload={"state": json.loads(state.model_dump_json()), "source": "agent"},
        merchant_id=merchant_id,
        timestamp=int(time.time() * 1000),
    )
    await manager.push_to_all(merchant_id, msg)
