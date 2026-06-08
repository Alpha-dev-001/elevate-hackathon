import { applyPatch, deepClone } from 'fast-json-patch'
import type { SystemState, JsonPatch, DeltaExecution } from '@/types'
import { getRedisClient, KEYS, TTL } from '@/lib/redis/client'

// ─── Delta Execution Engine ───────────────────────────────────────────────────
// Micro-mutations on global state. No full rewrites. Token-efficient by design.

export async function executeDelta(
  merchantId: string,
  actionId: string,
  patches: JsonPatch[],
  currentState: SystemState,
  executedBy: 'merchant' | 'auto' = 'merchant'
): Promise<{ newState: SystemState; execution: DeltaExecution }> {
  const redis = getRedisClient()

  // Deep clone for rollback capability
  const previousState = deepClone(currentState)

  // Apply patches
  const result = applyPatch(deepClone(currentState), patches, true, false)
  const newState: SystemState = {
    ...result.newDocument,
    version: currentState.version + 1,
    lastUpdated: Date.now(),
  }

  // Build execution record
  const execution: DeltaExecution = {
    actionId,
    patches,
    executedAt: Date.now(),
    executedBy,
    previousState,
    rollbackAvailable: true,
  }

  // Persist new state
  await redis.set(
    KEYS.systemState(merchantId),
    JSON.stringify(newState)
  )

  // Append to delta log (audit trail)
  await redis.lpush(
    KEYS.deltaLog(merchantId),
    JSON.stringify(execution)
  )
  await redis.expire(KEYS.deltaLog(merchantId), TTL.deltaLog)

  // Trim log to last 100 deltas
  await redis.ltrim(KEYS.deltaLog(merchantId), 0, 99)

  return { newState, execution }
}

// ─── Rollback last delta ──────────────────────────────────────────────────────

export async function rollbackLast(
  merchantId: string
): Promise<SystemState | null> {
  const redis = getRedisClient()

  const lastDeltaRaw = await redis.lindex(KEYS.deltaLog(merchantId), 0)
  if (!lastDeltaRaw) return null

  const lastDelta: DeltaExecution = JSON.parse(lastDeltaRaw)
  if (!lastDelta.rollbackAvailable) return null

  const restoredState: SystemState = {
    ...(lastDelta.previousState as SystemState),
    version: (lastDelta.previousState as SystemState).version,
    lastUpdated: Date.now(),
  }

  await redis.set(
    KEYS.systemState(merchantId),
    JSON.stringify(restoredState)
  )

  // Mark as rolled back
  await redis.lset(
    KEYS.deltaLog(merchantId),
    0,
    JSON.stringify({ ...lastDelta, rollbackAvailable: false })
  )

  return restoredState
}

// ─── Load current state ───────────────────────────────────────────────────────

export async function loadState(merchantId: string): Promise<SystemState | null> {
  const redis = getRedisClient()
  const raw = await redis.get(KEYS.systemState(merchantId))
  return raw ? JSON.parse(raw) : null
}

// ─── Stage a preview (sandbox — no persistence) ───────────────────────────────

export function stagePreview(
  currentState: SystemState,
  patches: JsonPatch[]
): SystemState {
  const clone = deepClone(currentState)
  const result = applyPatch(clone, patches, true, false)
  return {
    ...result.newDocument,
    version: currentState.version, // version doesn't increment for previews
    lastUpdated: Date.now(),
  }
}
