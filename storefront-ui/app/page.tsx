'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, ApiError } from '@/lib/api'
import type { Merchant } from '@/types/schemas'

export default function Home() {
  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    api.me()
      .then(setMerchant)
      .catch((e) => { if (!(e instanceof ApiError)) console.warn(e) })
      .finally(() => setChecked(true))
  }, [])

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-6xl font-bold tracking-tight mb-2" style={{ fontFamily: 'var(--font-display)' }}>Elevate</h1>
        <p className="text-muted text-lg">Your store, alive.</p>
      </div>

      {!checked ? (
        <p className="text-muted font-mono text-sm">…</p>
      ) : merchant ? (
        // Signed-in merchant: straight to the dashboard.
        <div className="flex flex-col items-center gap-3">
          <p className="text-muted text-sm">Signed in as {merchant.store_name}</p>
          <div className="flex gap-3">
            <Link href="/terminal" className="px-8 py-3 rounded-lg bg-accent text-bg hover:opacity-90 transition-opacity font-semibold text-sm accent-glow">
              Open dashboard →
            </Link>
            <Link href={`/s/${merchant.slug}`} className="px-8 py-3 rounded-lg border border-border text-text hover:opacity-80 transition-opacity font-semibold text-sm">
              View store ↗
            </Link>
          </div>
        </div>
      ) : (
        // Guest: build a new store, or sign in as an existing merchant.
        <div className="flex flex-col items-center gap-3">
          <Link href="/setup" className="px-8 py-3 rounded-lg bg-accent text-bg hover:opacity-90 transition-opacity font-semibold text-sm accent-glow">
            Build your store →
          </Link>
          <Link href="/login" className="text-sm text-muted underline">Merchant sign in</Link>
        </div>
      )}
    </main>
  )
}
