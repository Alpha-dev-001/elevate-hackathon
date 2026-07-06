'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion, useAnimationControls } from 'framer-motion'
import type { DashboardData } from '@/lib/api'

interface AttributionDashboardProps {
  data: DashboardData | null
  loading: boolean
}

function formatCurrency(value: number): string {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** Ease a displayed number from its previous value to the new one, so revenue
 * visibly counts up when a customer checks out (respects reduced-motion). */
function useCountUp(target: number, enabled: boolean, duration = 750): number {
  const [display, setDisplay] = useState(target)
  const fromRef = useRef(target)
  useEffect(() => {
    const from = fromRef.current
    if (!enabled || from === target) {
      fromRef.current = target
      setDisplay(target)
      return
    }
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
      setDisplay(from + (target - from) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, enabled, duration])
  return display
}

export function AttributionDashboard({ data, loading }: AttributionDashboardProps) {
  return (
    <section>
      {/* Section header */}
      <p
        className="text-xs font-mono font-semibold uppercase mb-4"
        style={{ color: 'var(--color-accent)', letterSpacing: '0.1em' }}
      >
        Attribution
      </p>

      {/* 3 metric cards */}
      <div className="flex flex-col gap-3 mb-6">
        <MetricCard label="Total Revenue" value={data ? data.total_gmv : null} loading={loading} />
        <MetricCard label="Elevate-Attributed" value={data ? data.elevate_attributed_gmv : null} loading={loading} accent />
        <MetricCard label="Your Fee (10%)" value={data ? data.elevate_fee : null} loading={loading} />
      </div>

      {/* Executed actions log */}
      {data && data.actions.length > 0 && (
        <div>
          <p
            className="text-xs font-mono uppercase mb-3"
            style={{ color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}
          >
            Executed Actions
          </p>
          <div className="flex flex-col gap-2">
            {data.actions.map((action) => (
              <div
                key={action.promo_id}
                className="rounded-lg p-3"
                style={{
                  background: 'var(--color-surface-2)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--color-text)' }}
                    >
                      {action.title}
                    </p>
                    <p
                      className="text-xs font-mono mt-0.5"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {action.attributed_orders} order{action.attributed_orders !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p
                      className="text-sm font-semibold"
                      style={{ color: 'var(--color-accent)' }}
                    >
                      {formatCurrency(action.attributed_gmv)}
                    </p>
                    <p
                      className="text-xs font-mono"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      fee {formatCurrency(action.fee)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data && data.actions.length === 0 && (
        <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
          No executed actions yet — approve an AI suggestion to see attribution here.
        </p>
      )}
    </section>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string
  value: number | null
  loading: boolean
  accent?: boolean
}

function MetricCard({ label, value, loading, accent }: MetricCardProps) {
  const prefersReduced = useReducedMotion()
  const controls = useAnimationControls()
  const prevRef = useRef<number | null>(value)

  const animated = useCountUp(value ?? 0, value != null && !prefersReduced)

  // Pulse the card the moment revenue increases — the live "money landed" beat.
  useEffect(() => {
    const prev = prevRef.current
    if (value != null && prev != null && value > prev && !prefersReduced) {
      controls.start({
        scale: [1, 1.035, 1],
        borderColor: ['var(--color-accent)', 'var(--color-accent)', accent ? 'var(--color-accent-dim)' : 'var(--color-border)'],
        transition: { duration: 0.6, ease: [0.4, 0, 0.2, 1] },
      })
    }
    prevRef.current = value
  }, [value, accent, controls, prefersReduced])

  return (
    <motion.div
      animate={controls}
      className="rounded-xl p-4"
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${accent ? 'var(--color-accent-dim)' : 'var(--color-border)'}`,
      }}
    >
      <p
        className="text-xs font-mono mb-2"
        style={{ color: 'var(--color-text-muted)', letterSpacing: '0.04em' }}
      >
        {label}
      </p>
      {loading && value == null ? (
        <motion.div
          animate={{ opacity: prefersReduced ? 0.5 : [0.3, 0.7, 0.3] }}
          transition={{ duration: 1.5, repeat: prefersReduced ? 0 : Infinity, ease: 'easeInOut' }}
          className="h-6 w-28 rounded"
          style={{ background: 'var(--color-surface-2)' }}
        />
      ) : (
        <p
          className="text-xl font-bold tabular-nums"
          style={{
            fontFamily: 'var(--font-mono)',
            color: accent ? 'var(--color-accent)' : 'var(--color-text)',
          }}
        >
          {value == null ? '—' : formatCurrency(animated)}
        </p>
      )}
    </motion.div>
  )
}
