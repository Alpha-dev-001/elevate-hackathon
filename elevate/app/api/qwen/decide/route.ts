import { NextRequest, NextResponse } from 'next/server'
import { requestDecision } from '@/lib/qwen/client'
import { validateDecision } from '@/lib/middleware/interceptor'
import { captureSnapshot } from '@/lib/redis/telemetry'
import { loadState } from '@/lib/patches/delta'
import { getRedisClient, KEYS, TTL } from '@/lib/redis/client'

// ─── POST /api/qwen/decide ────────────────────────────────────────────────────
// Captures telemetry snapshot → calls Qwen → validates decisions → queues for merchant

export async function POST(req: NextRequest) {
  try {
    const { merchantId, profile } = await req.json()

    if (!merchantId || !profile) {
      return NextResponse.json({ error: 'merchantId and profile required' }, { status: 400 })
    }

    // 1. Capture live telemetry snapshot
    const snapshot = await captureSnapshot(merchantId)

    // 2. Load current system state
    const currentState = await loadState(merchantId)
    if (!currentState) {
      return NextResponse.json({ error: 'System state not initialized' }, { status: 404 })
    }

    // 3. Request decision from Qwen
    const decision = await requestDecision({ snapshot, profile, currentState })

    // 4. Pass through subconscious interceptor (constraint validation)
    const validatedResults = validateDecision(decision.proposedActions, profile)

    const validatedActions = validatedResults
      .filter(r => r.valid)
      .map(r => r.action)

    const blockedActions = validatedResults
      .filter(r => !r.valid)
      .map(r => ({ action: r.action, violations: r.violations }))

    const clampedActions = validatedResults
      .filter(r => r.valid && r.clampedPatches)
      .map(r => ({ actionId: r.action.id, violations: r.violations }))

    // 5. Queue validated actions for merchant review
    const redis = getRedisClient()
    await redis.set(
      KEYS.pendingActions(merchantId),
      JSON.stringify(validatedActions),
      'EX',
      TTL.pendingActions
    )

    return NextResponse.json({
      decision: {
        ...decision,
        proposedActions: validatedActions,
      },
      snapshot,
      meta: {
        totalProposed: decision.proposedActions.length,
        validated: validatedActions.length,
        blocked: blockedActions.length,
        clamped: clampedActions.length,
        blockedDetails: blockedActions,
        clampedDetails: clampedActions,
      },
    })

  } catch (error) {
    console.error('[/api/qwen/decide]', error)
    return NextResponse.json(
      { error: 'Decision engine error', detail: (error as Error).message },
      { status: 500 }
    )
  }
}
