'use client'
import { useEffect, useState } from 'react'

/**
 * Live urgency countdown for an active promo. Ticks every second toward the
 * promo's expiry — the "10% off, ends in 09:58" that turns an approved recovery
 * offer into a reason to buy *now*. Renders nothing once expired (or before the
 * client clock is available, avoiding any hydration mismatch).
 */
export function PromoCountdown({ expiresAt }: { expiresAt: number }) {
  const [remaining, setRemaining] = useState<number | null>(null)

  useEffect(() => {
    const tick = () => setRemaining(Math.max(0, expiresAt - Date.now()))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [expiresAt])

  if (remaining === null || remaining <= 0) return null

  const total = Math.floor(remaining / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  const clock = h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`

  return (
    <span className="opacity-90">
      · ends in <span className="tabular-nums font-semibold">{clock}</span>
    </span>
  )
}
