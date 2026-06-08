import { NextRequest, NextResponse } from 'next/server'
import { executeDelta, stagePreview, loadState } from '@/lib/patches/delta'

// ─── POST /api/delta/apply ────────────────────────────────────────────────────
// Applies a merchant-approved action to the live system state

export async function POST(req: NextRequest) {
  try {
    const { merchantId, actionId, patches, mode } = await req.json()

    if (!merchantId || !actionId || !patches) {
      return NextResponse.json({ error: 'merchantId, actionId, patches required' }, { status: 400 })
    }

    const currentState = await loadState(merchantId)
    if (!currentState) {
      return NextResponse.json({ error: 'System state not found' }, { status: 404 })
    }

    // ── Staging mode: preview without persisting ──────────────────────────────
    if (mode === 'stage') {
      const preview = stagePreview(currentState, patches)
      return NextResponse.json({
        mode: 'staged',
        preview,
        diff: {
          before: currentState,
          after: preview,
        },
      })
    }

    // ── Live mode: execute and persist ────────────────────────────────────────
    const { newState, execution } = await executeDelta(
      merchantId,
      actionId,
      patches,
      currentState,
      'merchant'
    )

    return NextResponse.json({
      mode: 'executed',
      newState,
      execution,
      version: newState.version,
    })

  } catch (error) {
    console.error('[/api/delta/apply]', error)
    return NextResponse.json(
      { error: 'Delta execution failed', detail: (error as Error).message },
      { status: 500 }
    )
  }
}
