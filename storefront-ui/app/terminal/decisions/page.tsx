'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import type { Merchant } from '@/types/schemas'
import { DecisionLog } from '@/components/terminal/DecisionLog'

export default function DecisionsPage() {
  const router = useRouter()
  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setMerchant)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          router.push('/setup')
        }
      })
      .finally(() => setAuthLoading(false))
  }, [router])

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <p className="text-sm font-mono" style={{ color: 'var(--color-text-muted)' }}>Loading…</p>
      </div>
    )
  }

  if (!merchant) return null

  return (
    <main className="min-h-screen" style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}>
      <header
        className="sticky top-0 z-10 border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
      >
        <div>
          <h1 className="text-lg font-semibold" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
            Decision Trace
          </h1>
          <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
            {merchant.store_name} · every autopilot decision, with Qwen&apos;s own reasoning
          </p>
        </div>
        <a
          href="/terminal"
          className="text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
        >
          ← Back to terminal
        </a>
      </header>

      <div className="max-w-[820px] mx-auto px-6 pt-6 pb-16 flex flex-col gap-6">
        <div
          className="p-4 rounded-lg text-sm leading-relaxed"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}
        >
          <p className="mb-2">
            Nothing Qwen does is a black box. Every proposal below is a real row in the
            merchant&apos;s Postgres audit log — the trigger that fired it, the reasoning Qwen
            generated at decision time, and how the merchant responded (approved, dismissed, or
            auto-applied under graduated trust). Click <span style={{ color: 'var(--color-accent)' }}>&quot;why Qwen decided this&quot;</span> on
            any card to see the model&apos;s own explanation, verbatim, not a paraphrase — and
            <span style={{ color: 'var(--color-text)' }}> &quot;what Qwen was looking at&quot;</span> to
            see the actual catalog snapshot, prior-outcome memory, and discount ceiling that went
            into the prompt for that specific call.
          </p>
          <p>
            Revenue-impact estimates are grounded where possible — recovery and flash-sale
            proposals compute anomaly magnitude × this store&apos;s average product price × a fixed
            per-trigger rate, not a Qwen guess. Repricing and catalog-hygiene actions have no
            comparable real-world basis to ground against, so those fall back to Qwen&apos;s
            self-reported estimate, which the interceptor validates for safety (price floors,
            discount ceilings) but not for revenue accuracy.
          </p>
        </div>

        <DecisionLog merchantId={merchant.id} />
      </div>
    </main>
  )
}
