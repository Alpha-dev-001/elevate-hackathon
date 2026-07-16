import json
import logging
import time
import jsonpatch
from pydantic import ValidationError
from app.core.redis import get_redis, Keys, TTL
from app.models.schemas import SystemState, JsonPatch, DeltaExecution

logger = logging.getLogger(__name__)


async def load_state(merchant_id: str) -> SystemState | None:
    """Redis is a cache, never the only copy of anything important — a cached
    SystemState blob written before a field (e.g. baseline_price) existed on
    Product must not 500 every request against this store forever. On a
    validation failure, self-heal: backfill any missing product field with a
    sensible default (baseline_price falls back to that product's own price,
    the same anchor semantics the field was introduced with) and re-validate.
    A genuinely corrupt blob (not just stale-schema) still raises, since that
    signals something worse than an additive field."""
    redis = await get_redis()
    raw = await redis.get(Keys.system_state(merchant_id))
    if not raw:
        return None
    try:
        return SystemState.model_validate_json(raw)
    except ValidationError as e:
        logger.warning(f"[delta] stale-schema state for {merchant_id}, repairing: {e}")
        repaired = _repair_stale_products(json.loads(raw))
        state = SystemState.model_validate(repaired)
        await save_state(merchant_id, state)  # write the repair back so it self-heals once
        return state


def _repair_stale_products(state_dict: dict) -> dict:
    for product in (state_dict.get("products") or {}).values():
        if product.get("baseline_price") is None:
            product["baseline_price"] = product.get("price", 0.0)
    return state_dict


async def save_state(merchant_id: str, state: SystemState) -> None:
    redis = await get_redis()
    await redis.set(Keys.system_state(merchant_id), state.model_dump_json())


async def execute_delta(
    merchant_id: str,
    action_id: str,
    patches: list[JsonPatch],
    current_state: SystemState,
    executed_by: str = "merchant",
) -> tuple[SystemState, DeltaExecution]:
    redis = await get_redis()

    # Serialize patches for jsonpatch library
    patch_list = [
        {k: v for k, v in p.model_dump(by_alias=True).items() if v is not None}
        for p in patches
    ]

    # Apply patches to state dict
    state_dict = json.loads(current_state.model_dump_json())
    patched = jsonpatch.apply_patch(state_dict, patch_list)

    new_state = SystemState.model_validate({
        **patched,
        "version": current_state.version + 1,
        "last_updated": int(time.time() * 1000),
    })

    execution = DeltaExecution(
        action_id=action_id,
        patches=patches,
        executed_at=int(time.time() * 1000),
        executed_by=executed_by,
        rollback_available=True,
    )

    # Persist new state
    await redis.set(Keys.system_state(merchant_id), new_state.model_dump_json())

    # Append to delta log (audit trail, last 100)
    await redis.lpush(Keys.delta_log(merchant_id), execution.model_dump_json())
    await redis.ltrim(Keys.delta_log(merchant_id), 0, 99)
    await redis.expire(Keys.delta_log(merchant_id), TTL.DELTA_LOG)

    return new_state, execution


def stage_preview(current_state: SystemState, patches: list[JsonPatch]) -> SystemState:
    """Apply patches in memory only — no persistence. Sandbox preview."""
    patch_list = [
        {k: v for k, v in p.model_dump(by_alias=True).items() if v is not None}
        for p in patches
    ]
    state_dict = json.loads(current_state.model_dump_json())
    patched = jsonpatch.apply_patch(state_dict, patch_list)
    return SystemState.model_validate({
        **patched,
        "version": current_state.version,  # no version bump for previews
        "last_updated": int(time.time() * 1000),
    })


async def rollback_last(merchant_id: str) -> SystemState | None:
    redis = await get_redis()
    raw = await redis.lindex(Keys.delta_log(merchant_id), 0)
    if not raw:
        return None

    last: DeltaExecution = DeltaExecution.model_validate_json(raw)
    if not last.rollback_available:
        return None

    # The previous state is stored in Redis before each delta
    prev_raw = await redis.get(f"{Keys.system_state(merchant_id)}:prev")
    if not prev_raw:
        return None

    prev_state = SystemState.model_validate_json(prev_raw)
    await redis.set(Keys.system_state(merchant_id), prev_raw)

    return prev_state
