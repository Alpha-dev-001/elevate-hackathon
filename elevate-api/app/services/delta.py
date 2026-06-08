import json
import time
import jsonpatch
from app.core.redis import get_redis, Keys, TTL
from app.models.schemas import SystemState, JsonPatch, DeltaExecution


async def load_state(merchant_id: str) -> SystemState | None:
    redis = await get_redis()
    raw = await redis.get(Keys.system_state(merchant_id))
    return SystemState.model_validate_json(raw) if raw else None


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
