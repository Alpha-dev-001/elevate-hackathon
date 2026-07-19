'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { api, type EligibleTrust } from '@/lib/api'

// ── Reduced-motion hook (mirrors DecisionFeed/CapabilityProposals) ──────────
function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return reduced
}

function humanizeActionType(actionType: string): string {
  return actionType.replace(/_/g, ' ')
}

interface EarnedTrustPanelProps {
  eligible: EligibleTrust[]
  onToggled: (updated: EligibleTrust) => void
}

/**
 * Earning a streak unlocks the OPTION to let Qwen auto-apply small,
 * already-safe price moves on a specific product — it never flips the
 * switch by itself. This panel is where the merchant makes that call,
 * discoverable whenever they're on the terminal, not sprung on them as a
 * one-time interrupt. Pure/props-driven (page owns the fetch), renders
 * nothing until at least one product has actually earned it.
 */
export function EarnedTrustPanel({ eligible, onToggled }: EarnedTrustPanelProps) {
  const prefersReduced = useReducedMotion()
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (eligible.length === 0) return null

  async function handleToggle(item: EligibleTrust) {
    const key = `${item.product_id}:${item.action_type}`
    if (pending) return
    setPending(key)
    try {
      const result = await api.toggleAutopilotTrust(item.product_id, item.action_type, !item.auto_apply_enabled)
      onToggled({ ...item, auto_apply_enabled: result.enabled })
    } catch {
      setError('Toggle failed — try again')
      setTimeout(() => setError(null), 3000)
    } finally {
      setPending(null)
    }
  }

  return (
    <motion.section
      data-testid="earned-trust-panel"
      initial={prefersReduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
      className="rounded-xl border p-4 mb-6"
      style={{
        borderColor: 'var(--color-accent)',
        background: 'var(--color-accent-dim, rgba(110,231,183,0.08))',
      }}
    >
      <div className="flex items-baseline gap-2 mb-1">
        <span
          className="text-sm font-semibold"
          style={{ fontFamily: 'var(--font-display)', color: 'var(--color-accent)' }}
        >
          ✦ Earned trust — {eligible.length} {eligible.length === 1 ? 'product' : 'products'}
        </span>
      </div>
      <p className="text-xs font-mono mb-3" style={{ color: 'var(--color-text-muted)' }}>
        Qwen has kept small moves on these within your safe range at least 3 times in a row.
        You decide whether it can apply the next one without waiting for your approval.
      </p>

      <ul className="flex flex-col gap-2">
        {eligible.map((item) => {
          const key = `${item.product_id}:${item.action_type}`
          const isPending = pending === key
          return (
            <li
              key={key}
              className="rounded-lg border px-3 py-2 flex items-center justify-between gap-3"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
            >
              <div className="min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--color-text)' }}>
                  {item.product_name}
                </p>
                <p className="text-xs font-mono capitalize" style={{ color: 'var(--color-text-muted)' }}>
                  {humanizeActionType(item.action_type)} · streak {item.streak}
                </p>
              </div>
              <button
                onClick={() => handleToggle(item)}
                disabled={isPending}
                className="shrink-0 rounded-md py-1.5 px-3 text-xs font-semibold transition-opacity disabled:opacity-50"
                style={{
                  background: item.auto_apply_enabled ? 'var(--color-accent)' : 'transparent',
                  color: item.auto_apply_enabled ? 'var(--color-bg)' : 'var(--color-text-muted)',
                  border: `1px solid ${item.auto_apply_enabled ? 'var(--color-accent)' : 'var(--color-border)'}`,
                }}
              >
                {item.auto_apply_enabled ? 'Auto-apply: ON' : 'Auto-apply: OFF'}
              </button>
            </li>
          )
        })}
      </ul>

      {error && (
        <p className="text-xs mt-2 font-mono" style={{ color: 'var(--color-danger)' }}>
          {error}
        </p>
      )}
    </motion.section>
  )
}
