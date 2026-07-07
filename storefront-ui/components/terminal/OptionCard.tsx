'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { IconBolt } from '@/components/icons'
import type { AgentAction } from '@/types/schemas'

// ── Reduced-motion hook ──────────────────────────────────────────────────────

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

// ── Action type metadata ─────────────────────────────────────────────────────

interface ActionTypeMeta {
  label: string
  badgeBg: string
  badgeText: string
}

const ACTION_TYPE_META: Record<string, ActionTypeMeta> = {
  flash_sale:    { label: 'Flash Sale',       badgeBg: 'var(--color-warning)', badgeText: '#0A0A0B' },
  layout_morph:  { label: 'Layout Shift',     badgeBg: 'var(--color-accent)',  badgeText: '#0A0A0B' },
  recovery_offer:{ label: 'Win-Back Offer',   badgeBg: '#3B82F6',              badgeText: '#ffffff' },
  scarcity_price:{ label: 'Scarcity Pricing', badgeBg: '#F97316',              badgeText: '#ffffff' },
  copy_rewrite:  { label: 'Copy Rewrite',     badgeBg: '#8B5CF6',              badgeText: '#ffffff' },
}

function getTypeMeta(actionType: string): ActionTypeMeta {
  return ACTION_TYPE_META[actionType] ?? {
    label: actionType.replace(/_/g, ' '),
    badgeBg: 'var(--color-border)',
    badgeText: 'var(--color-text)',
  }
}

// ── Props ────────────────────────────────────────────────────────────────────

interface OptionCardProps {
  action: AgentAction
  /** Called with the action id after a successful approve. Parent removes it from the list. */
  onApprove: (id: string) => void
  /** Called with the action id after a successful dismiss. */
  onDismiss: (id: string) => void
  /** Entry stagger delay in seconds */
  delay?: number
}

// ── Component ────────────────────────────────────────────────────────────────

export function OptionCard({ action, onApprove, onDismiss, delay = 0 }: OptionCardProps) {
  const reduced = useReducedMotion()
  const duration = reduced ? 0 : 0.45
  const microDuration = reduced ? 0 : 0.15

  const [isApproving, setIsApproving] = useState(false)
  const [isDismissing, setIsDismissing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isLoading = isApproving || isDismissing
  const confidencePct = Math.round(action.estimated_confidence * 100)
  const meta = getTypeMeta(action.action_type)

  function showError(msg: string) {
    setError(msg)
    setTimeout(() => setError(null), 3000)
  }

  async function handleApprove() {
    if (isLoading) return
    setIsApproving(true)
    try {
      await api.approveAction(action.id)
      onApprove(action.id)
    } catch {
      showError('Action failed — try again')
    } finally {
      setIsApproving(false)
    }
  }

  async function handleDismiss() {
    if (isLoading) return
    setIsDismissing(true)
    try {
      await api.dismissAction(action.id)
      onDismiss(action.id)
    } catch {
      showError('Dismiss failed — try again')
    } finally {
      setIsDismissing(false)
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{
        duration,
        delay,
        ease: [0.4, 0, 0.2, 1],
      }}
      style={{
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-lg)',
        padding: '20px',
      }}
    >
      {/* Action type badge */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className="text-xs font-mono font-semibold px-2 py-0.5 rounded"
          style={{
            background: meta.badgeBg,
            color: meta.badgeText,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {meta.label}
        </span>
      </div>

      {/* Trigger */}
      <p className="text-xs font-mono mb-3 flex items-center gap-1.5" style={{ color: 'var(--color-warning)' }}>
        <IconBolt size={13} /> {action.trigger}
      </p>

      {/* Title */}
      <h3
        className="text-base font-bold mb-1 leading-snug"
        style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
      >
        {action.title}
      </h3>

      {/* Description */}
      <p className="text-sm mb-4" style={{ color: 'var(--color-text-muted)', lineHeight: '1.5' }}>
        {action.description}
      </p>

      {/* GMV Impact */}
      <p className="text-sm font-semibold mb-3" style={{ color: 'var(--color-accent)' }}>
        Est. Revenue Impact: +${action.estimated_gmv.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
      </p>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
            Confidence
          </span>
          <span className="text-xs font-mono font-semibold" style={{ color: 'var(--color-accent)' }}>
            {confidencePct}%
          </span>
        </div>
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ background: 'var(--color-border)' }}
        >
          <motion.div
            className="h-full rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${confidencePct}%` }}
            transition={{ duration: reduced ? 0 : 0.6, ease: [0.4, 0, 0.2, 1], delay: delay + 0.1 }}
            style={{ background: 'var(--color-accent)' }}
          />
        </div>
      </div>

      {/* Brand alignment */}
      {action.brand_check && (
        <p className="text-xs italic mb-4" style={{ color: 'var(--color-text-muted)' }}>
          Brand alignment: {action.brand_check}
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs mb-3 font-mono" style={{ color: 'var(--color-danger)' }}>
          {error}
        </p>
      )}

      {/* Buttons */}
      <div className="flex gap-3">
        <motion.button
          onClick={handleApprove}
          disabled={isLoading}
          whileTap={{ scale: reduced ? 1 : 0.96 }}
          whileHover={{ opacity: isLoading ? 0.7 : 0.9 }}
          transition={{ duration: microDuration }}
          className="flex-1 py-2.5 rounded-lg text-sm font-bold cursor-pointer disabled:cursor-not-allowed"
          style={{
            background: isLoading ? 'var(--color-accent-dim)' : 'var(--color-accent)',
            color: 'var(--color-bg)',
            transition: `background ${microDuration}s, opacity ${microDuration}s`,
            opacity: isLoading ? 0.7 : 1,
          }}
        >
          {isApproving ? 'Applying…' : 'Approve'}
        </motion.button>

        <motion.button
          onClick={handleDismiss}
          disabled={isLoading}
          whileTap={{ scale: reduced ? 1 : 0.96 }}
          whileHover={{ borderColor: 'var(--color-accent)' }}
          transition={{ duration: microDuration }}
          className="px-5 py-2.5 rounded-lg text-sm cursor-pointer disabled:cursor-not-allowed"
          style={{
            border: '1px solid var(--color-border)',
            color: isLoading ? 'var(--color-text-muted)' : 'var(--color-text)',
            background: 'transparent',
            transition: `color ${microDuration}s, border-color ${microDuration}s`,
          }}
        >
          {isDismissing ? 'Dismissing…' : 'Dismiss'}
        </motion.button>
      </div>
    </motion.div>
  )
}
