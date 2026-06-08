import { NextRequest, NextResponse } from 'next/server'
import { recordEvent } from '@/lib/redis/telemetry'
import type { CustomerEvent } from '@/types'

// ─── POST /api/telemetry/snapshot ─────────────────────────────────────────────
// Ingests customer events from the storefront in real time

export async function POST(req: NextRequest) {
  try {
    const { merchantId, event }: { merchantId: string; event: CustomerEvent } = await req.json()

    if (!merchantId || !event) {
      return NextResponse.json({ error: 'merchantId and event required' }, { status: 400 })
    }

    await recordEvent(merchantId, event)

    return NextResponse.json({ recorded: true })

  } catch (error) {
    console.error('[/api/telemetry/snapshot]', error)
    return NextResponse.json(
      { error: 'Event recording failed' },
      { status: 500 }
    )
  }
}
