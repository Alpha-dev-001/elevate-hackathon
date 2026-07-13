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

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_merchant
from app.models.db_models import AgentActionDB, MerchantDB, ProductDB
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
        reasoning=row.reasoning or "",
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
async def approve_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    merchant: MerchantDB = Depends(get_current_merchant),
):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    if row.merchant_id != merchant.id:
        raise HTTPException(status_code=403, detail="This action belongs to a different store")
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
    """The expiry ms of this action's promo/recovery — the same duration the
    execution used — so the outcome observer fires when the offer actually ends."""
    return _payload_duration_ms(row.payload or {})


@router.post("/actions/{action_id}/dismiss")
async def dismiss_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    merchant: MerchantDB = Depends(get_current_merchant),
):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    if row.merchant_id != merchant.id:
        raise HTTPException(status_code=403, detail="This action belongs to a different store")
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

    if row.action_type == "duplicate_merge":
        try:
            from app.services.duplicate_scan import suppress_duplicate_group
            from app.core.redis import get_redis
            payload = row.payload or {}
            keep_id = payload.get("keep_product_id")
            remove_ids = payload.get("remove_product_ids") or []
            group_ids = ([keep_id] if keep_id else []) + list(remove_ids)
            if len(group_ids) >= 2:
                await suppress_duplicate_group(row.merchant_id, group_ids, await get_redis())
        except Exception as e:  # noqa: BLE001 — suppression must never block a dismiss
            logger.warning("[agent] duplicate-merge suppression failed for %s: %s", row.id, e)

    return {"action": _to_schema(row).model_dump()}


# Product-scoped revenue actions register a real, attributable Promo on a
# product so the dashboard can measure what the AI drove. recovery_offer is NOT
# here on purpose — a cart-recovery discount is order-level (see _register_recovery),
# it must not blanket-discount the browse grid. Labels only; the discount depth is
# Qwen's payload, falling back to the per-type config default.
_PROMO_LABELS = {
    "flash_sale":     "Flash Sale — {d}% off",
    "scarcity_price": "Limited time — {d}% off",
}


def _default_discount(action_type: str) -> float:
    """The deterministic fallback discount for an action type, from config —
    used only when Qwen's payload omits discount_percent."""
    s = get_settings()
    return {
        "flash_sale": s.flash_sale_default_discount_percent,
        "scarcity_price": s.scarcity_default_discount_percent,
        "recovery_offer": s.recovery_default_discount_percent,
    }.get(action_type, s.recovery_default_discount_percent)


def _payload_discount(payload: dict, default: float, ceiling: float) -> float:
    """Qwen's chosen discount (or the config default), floored above 0 so it stays
    attributable and clamped to the merchant's max_discount_percent ceiling
    (interceptor Layer 2) — never a magic hardcoded cap."""
    try:
        d = float(payload.get("discount_percent") or default)
    except (TypeError, ValueError):
        d = float(default)
    return max(1.0, min(float(ceiling), d))


def _payload_duration_ms(payload: dict, default_minutes: int | None = None) -> int:
    default_minutes = default_minutes or get_settings().agent_action_duration_minutes
    try:
        minutes = int(payload.get("duration_minutes") or default_minutes)
    except (TypeError, ValueError):
        minutes = default_minutes
    return int(time.time() * 1000) + minutes * 60 * 1000


async def _register_promo(row: AgentActionDB, label_tmpl: str, payload: dict, db: AsyncSession) -> None:
    """Create an attributable Promo in live state for a revenue action.

    Targets the product Qwen identified in its tool call (payload["product_id"]).
    Falls back to the first product if Qwen didn't specify one or the specified
    product isn't in the live state.
    """
    from app.services import delta as delta_svc
    from app.services.profile import load_constraints
    from app.models.schemas import Promo

    state = await delta_svc.load_state(row.merchant_id)
    if not state:
        logger.warning(
            "[agent] %s: state not found for merchant %s — promo not applied",
            row.action_type, row.merchant_id,
        )
        return

    # Qwen's discount, floored >0 and clamped to the merchant's discount ceiling.
    constraints = await load_constraints(db, row.merchant_id)
    discount = _payload_discount(payload, _default_discount(row.action_type), constraints.max_discount_percent)
    expires_at = _payload_duration_ms(payload)

    # Use the product Qwen targeted. Fall back to first product if not specified
    # or not in state (e.g. product was deactivated between decision and approval).
    target_pid = payload.get("product_id")
    if target_pid and target_pid in state.products:
        product_id = target_pid
    else:
        product_id = list(state.products.keys())[0] if state.products else "all"
        if target_pid:
            logger.info(
                "[agent] %s: Qwen targeted product %s but it's not in state, falling back to %s",
                row.action_type, target_pid, product_id,
            )

    promo = Promo(
        id=row.promo_id,
        product_id=product_id,
        discount_percent=discount,
        label=label_tmpl.format(d=int(discount)),
        expires_at=expires_at,
        triggered_by="auto",
    )
    state.active_promos[row.promo_id] = promo
    await delta_svc.save_state(row.merchant_id, state)
    logger.info("[agent] %s registered promo %s (%d%%) on product %s", row.action_type, row.promo_id, int(discount), product_id)


async def _register_recovery(row: AgentActionDB, payload: dict, db: AsyncSession) -> None:
    """Set the merchant's active ORDER-LEVEL cart-recovery discount.

    This is the correct shape for a cart-abandon recovery: it discounts the
    shopper's existing cart total (applied in cart._apply_recovery), and leaves
    every product on the browse grid at full price. It still carries this action's
    promo_id so a checkout under the offer attributes to it in the dashboard.
    """
    from app.services import delta as delta_svc
    from app.services.profile import load_constraints
    from app.models.schemas import RecoveryOffer

    state = await delta_svc.load_state(row.merchant_id)
    if not state:
        logger.warning(
            "[agent] recovery_offer: state not found for merchant %s — recovery not applied",
            row.merchant_id,
        )
        return

    # Qwen chooses the depth; clamp to the merchant's discount ceiling (Layer 2).
    constraints = await load_constraints(db, row.merchant_id)
    discount = _payload_discount(payload, _default_discount("recovery_offer"), constraints.max_discount_percent)
    state.recovery = RecoveryOffer(
        percent=discount,
        label=f"Complete your order — {int(discount)}% off",
        expires_at=_payload_duration_ms(payload),
        promo_id=row.promo_id,
        triggered_by="auto",
    )
    await delta_svc.save_state(row.merchant_id, state)
    logger.info("[agent] recovery_offer set order-level recovery %d%% (promo %s)", int(discount), row.promo_id)


async def _execute_payload(row: AgentActionDB, db: AsyncSession) -> None:
    """Apply the action's payload to the live store state."""
    from app.services import delta as delta_svc

    payload = row.payload or {}

    if row.action_type == "recovery_offer":
        await _register_recovery(row, payload, db)

    elif row.action_type in _PROMO_LABELS:
        await _register_promo(row, _PROMO_LABELS[row.action_type], payload, db)

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

    elif row.action_type == "duplicate_merge":
        keep_id = payload.get("keep_product_id")
        # Defense against Qwen hallucination: if keep_product_id ever also
        # shows up inside remove_product_ids, the kept listing would be
        # deactivated along with the removed ones, leaving the product with
        # zero active listings. Filter it out of the removal set.
        remove_ids = [pid for pid in (payload.get("remove_product_ids") or []) if pid != keep_id]
        if remove_ids:
            rows = (await db.execute(
                select(ProductDB)
                .where(ProductDB.id.in_(remove_ids))
                .where(ProductDB.merchant_id == row.merchant_id)  # defense in depth — scope to this merchant
            )).scalars().all()
            if rows:
                for p in rows:
                    p.is_active = False
                await db.flush()
                # Imported here, not at the top of _execute_payload — matches
                # this file's existing convention (_register_promo/_register_recovery
                # import their own branch-specific dependencies locally too).
                from app.routers.products import _sync_state_if_live
                await _sync_state_if_live(db, row.merchant_id)
                logger.info(
                    "[agent] duplicate_merge deactivated %d product(s) for %s",
                    len(rows), row.merchant_id,
                )
            else:
                logger.info(
                    "[agent] duplicate_merge: no matching products found for %s (already removed?)",
                    row.id,
                )

    elif row.action_type == "feature_product":
        target_pid = payload.get("product_id")
        if target_pid:
            # Unset any previously-featured product first — one clear pick,
            # not a second spotlight competing with the main grid.
            previously_featured = (await db.execute(
                select(ProductDB)
                .where(ProductDB.merchant_id == row.merchant_id)
                .where(ProductDB.is_featured == True)
            )).scalars().all()
            for p in previously_featured:
                p.is_featured = False

            target = await db.get(ProductDB, target_pid)
            if target and target.merchant_id == row.merchant_id:
                target.is_featured = True
                target.featured_label = str(payload.get("featured_label", "New Arrival"))[:80]
                await db.flush()
                from app.routers.products import _sync_state_if_live
                await _sync_state_if_live(db, row.merchant_id)
                logger.info("[agent] featured product %s for %s", target_pid, row.merchant_id)
            else:
                logger.info(
                    "[agent] feature_product: target %s not found for %s (already removed?)",
                    target_pid, row.id,
                )

    # copy_rewrite and any unknown type — not a promo/layout action; log only.
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
