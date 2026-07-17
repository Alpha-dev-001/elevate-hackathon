'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '@/lib/api'
import { IconBolt } from '@/components/icons'
import type { AgentAction } from '@/types/schemas'

// ── Pending action TTL (must match backend config: pending_action_ttl_seconds) ─
const PENDING_ACTION_TTL_MS = 5 * 60 * 1000 // 5 minutes

// ── Dismiss-confirm window for duplicate_merge only (must exceed nothing on
// the backend — this is purely client-side, the real dismiss call is just
// delayed until this elapses) ───────────────────────────────────────────────
const UNDO_WINDOW_MS = 5000

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
  flash_sale:      { label: 'Flash Sale',       badgeBg: 'var(--color-warning)', badgeText: '#0A0A0B' },
  layout_morph:    { label: 'Layout Shift',     badgeBg: 'var(--color-accent)',  badgeText: '#0A0A0B' },
  recovery_offer:  { label: 'Win-Back Offer',   badgeBg: '#3B82F6',              badgeText: '#ffffff' },
  scarcity_price:  { label: 'Scarcity Pricing', badgeBg: '#F97316',              badgeText: '#ffffff' },
  copy_rewrite:    { label: 'Copy Rewrite',     badgeBg: '#8B5CF6',              badgeText: '#ffffff' },
  duplicate_merge: { label: 'Duplicate Cleanup',badgeBg: '#22C55E',              badgeText: '#ffffff' },
  price_rebalance: { label: 'Price Rebalance',  badgeBg: '#EAB308',              badgeText: '#0A0A0B' },
  cart_dwell_nudge:{ label: 'Cart Nudge',        badgeBg: '#06B6D4',              badgeText: '#0A0A0B' },
}

function getTypeMeta(actionType: string): ActionTypeMeta {
  return ACTION_TYPE_META[actionType] ?? {
    label: actionType.replace(/_/g, ' '),
    badgeBg: 'var(--color-border)',
    badgeText: 'var(--color-text)',
  }
}

const ROLE_LABELS: Record<string, string> = {
  pricing_strategist: 'Pricing Strategist',
  sales_rep: 'Sales Rep',
  inventory_overseer: 'Inventory Overseer',
  store_curator: 'Store Curator',
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
  const [showReasoning, setShowReasoning] = useState(false)
  const [pendingUndo, setPendingUndo] = useState(false)
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Merchant can override Qwen's proposed discount before approving — still
  // clamped by the interceptor server-side, this just lets the merchant
  // correct the number instead of only approve/reject as-is.
  const DISCOUNT_ACTION_TYPES = new Set([
    'flash_sale', 'scarcity_price', 'recovery_offer', 'cart_dwell_nudge',
  ])
  const hasDiscount = DISCOUNT_ACTION_TYPES.has(action.action_type) && typeof action.payload?.discount_percent === 'number'
  const [overridePercent, setOverridePercent] = useState<string>(
    hasDiscount ? String(action.payload.discount_percent) : ''
  )

  useEffect(() => {
    return () => {
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current)
    }
  }, [])

  // Track card age for TTL expiry display
  const [ageSeconds, setAgeSeconds] = useState(() =>
    Math.max(0, Math.floor((Date.now() - action.created_at) / 1000))
  )
  useEffect(() => {
    const interval = setInterval(() => {
      setAgeSeconds(Math.max(0, Math.floor((Date.now() - action.created_at) / 1000)))
    }, 15_000) // update every 15s
    return () => clearInterval(interval)
  }, [action.created_at])

  const isExpired = ageSeconds >= PENDING_ACTION_TTL_MS / 1000
  const ageLabel = ageSeconds < 60 ? `${ageSeconds}s ago` : `${Math.floor(ageSeconds / 60)}m ago`

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
      const parsed = parseFloat(overridePercent)
      const override = hasDiscount && !Number.isNaN(parsed) && parsed !== action.payload.discount_percent
        ? { discount_percent_override: parsed }
        : undefined
      const { action: updated } = await api.approveAction(action.id, override)
      if (updated.status === 'blocked_at_execution') {
        // State drifted unsafe between proposal and approval (e.g. cost changed) —
        // the interceptor's execution-time re-check blocked it. Keep the card
        // visible and tell the merchant plainly; do NOT treat this as success.
        showError('Blocked at approval — store conditions changed, this did not go live')
      } else {
        onApprove(action.id)
      }
    } catch {
      showError('Action failed — try again')
    } finally {
      setIsApproving(false)
    }
  }

  async function commitDismiss() {
    setIsDismissing(true)
    try {
      await api.dismissAction(action.id)
      onDismiss(action.id)
    } catch {
      showError('Dismiss failed — try again')
      setPendingUndo(false) // restore the card so the merchant can retry
    } finally {
      setIsDismissing(false)
    }
  }

  async function handleDismiss() {
    if (isLoading || pendingUndo) return

    // duplicate_merge dismissals set a week-long suppression on the backend —
    // a misclick shouldn't silently create that blind spot. Every other
    // action type (and an already-expired duplicate_merge card, which has
    // nothing left to suppress against) keeps today's instant dismiss.
    const needsConfirm = action.action_type === 'duplicate_merge' && !isExpired
    if (needsConfirm) {
      setPendingUndo(true)
      undoTimerRef.current = setTimeout(() => {
        undoTimerRef.current = null
        commitDismiss()
      }, UNDO_WINDOW_MS)
      return
    }

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

  function handleUndo() {
    if (!undoTimerRef.current) return // timer already fired, commit in progress — nothing to undo
    clearTimeout(undoTimerRef.current)
    undoTimerRef.current = null
    setPendingUndo(false)
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
      {pendingUndo ? (
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-mono" style={{ color: 'var(--color-text-muted)' }}>
            Duplicate merge dismissed
          </p>
          <motion.button
            onClick={handleUndo}
            disabled={isDismissing}
            whileTap={{ scale: reduced ? 1 : 0.96 }}
            transition={{ duration: microDuration }}
            className="text-sm font-bold cursor-pointer px-3 py-1.5 rounded-lg disabled:cursor-not-allowed"
            style={{
              color: 'var(--color-accent)',
              border: '1px solid var(--color-accent)',
              opacity: isDismissing ? 0.7 : 1,
            }}
          >
            Undo
          </motion.button>
        </div>
      ) : (
        <>
          {/* Action type badge + role badge + age */}
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span
              className="text-xs font-mono font-semibold px-2 py-0.5 rounded"
              style={{
                background: isExpired ? 'var(--color-border)' : meta.badgeBg,
                color: isExpired ? 'var(--color-text-muted)' : meta.badgeText,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              {isExpired ? 'Expired' : meta.label}
            </span>
            {action.role && ROLE_LABELS[action.role] && (
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                ✦ {ROLE_LABELS[action.role]}
              </span>
            )}
            <span
              className="text-[10px] font-mono"
              style={{ color: isExpired ? 'var(--color-danger)' : 'var(--color-text-muted)' }}
            >
              ⏱ {ageLabel}
            </span>
          </div>

          {/* Expired signal banner */}
          {isExpired && (
            <p className="text-xs font-mono mb-3 px-2 py-1.5 rounded" style={{
              background: 'rgba(255, 107, 107, 0.1)',
              color: 'var(--color-danger)',
              border: '1px solid rgba(255, 107, 107, 0.2)',
            }}>
              Signal expired — the anomaly that triggered this has likely resolved. Dismiss or approve anyway.
            </p>
          )}

          {/* Trigger */}
          <p className="text-xs font-mono mb-3 flex items-center gap-1.5" style={{ color: 'var(--color-warning)' }}>
            <IconBolt size={13} /> {action.trigger}
          </p>

          {/* Targeted product — show when Qwen's tool call identified a specific product */}
          {action.payload?.product_id && (
            <p className="text-[10px] font-mono mb-3 flex items-center gap-1.5" style={{ color: 'var(--color-text-muted)' }}>
              <span
                className="px-1.5 py-0.5 rounded"
                style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
              >
                ⎯ Target: {String(action.payload.product_id).slice(0, 12)}
              </span>
            </p>
          )}

          {/* Title */}
          <h3
            className="text-base font-bold mb-1 leading-snug"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
          >
            {action.title}
          </h3>

          {/* Description */}
          <p className="text-sm mb-3" style={{ color: 'var(--color-text-muted)', lineHeight: '1.5' }}>
            {action.description}
          </p>

          {/* Qwen's Reasoning — collapsible chain-of-thought */}
          {action.reasoning && (
            <div className="mb-4">
              <button
                onClick={() => setShowReasoning(!showReasoning)}
                className="text-[10px] font-mono uppercase tracking-widest flex items-center gap-1.5 transition-colors"
                style={{ color: showReasoning ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
              >
                <span style={{ transform: showReasoning ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s', display: 'inline-block' }}>▸</span>
                ✦ Qwen&apos;s reasoning
              </button>
              <AnimatePresence>
                {showReasoning && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <p
                      className="text-xs font-mono leading-relaxed mt-2 pl-3 border-l-2"
                      style={{
                        color: 'var(--color-accent)',
                        borderColor: 'var(--color-accent)',
                        opacity: 0.85,
                      }}
                    >
                      {action.reasoning}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

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

          {/* Constraint check — Layer 2/3, only shown when something was clamped */}
          {action.constraint_check && (
            <p className="text-xs italic mb-4" style={{ color: 'var(--color-warning)' }}>
              Constraint check: {action.constraint_check}
            </p>
          )}

          {/* Discount override — only for action types that carry a discount_percent */}
          {hasDiscount && (
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <label className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
                Discount %
              </label>
              <input
                type="number" min={0} max={100} step={1}
                value={overridePercent}
                onChange={(e) => setOverridePercent(e.target.value)}
                disabled={isLoading}
                className="w-16 rounded px-2 py-1 text-xs font-mono outline-none disabled:opacity-50"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
              <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                Qwen proposed {action.payload.discount_percent}% — still clamped to your settings ceiling
              </span>
            </div>
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
                background: isExpired
                  ? 'transparent'
                  : isLoading ? 'var(--color-accent-dim)' : 'var(--color-accent)',
                border: isExpired ? '1px solid var(--color-border)' : 'none',
                color: isExpired ? 'var(--color-text-muted)' : 'var(--color-bg)',
                transition: `background ${microDuration}s, opacity ${microDuration}s`,
                opacity: isLoading ? 0.7 : 1,
              }}
            >
              {isApproving ? 'Applying…' : isExpired ? 'Approve anyway' : 'Approve'}
            </motion.button>

            <motion.button
              onClick={handleDismiss}
              disabled={isLoading}
              whileTap={{ scale: reduced ? 1 : 0.96 }}
              whileHover={{ borderColor: isExpired ? 'var(--color-danger)' : 'var(--color-accent)' }}
              transition={{ duration: microDuration }}
              className="px-5 py-2.5 rounded-lg text-sm cursor-pointer disabled:cursor-not-allowed"
              style={{
                border: `1px solid ${isExpired ? 'var(--color-danger)' : 'var(--color-border)'}`,
                color: isExpired
                  ? 'var(--color-danger)'
                  : isLoading ? 'var(--color-text-muted)' : 'var(--color-text)',
                background: isExpired ? 'rgba(255, 107, 107, 0.08)' : 'transparent',
                fontWeight: isExpired ? 600 : 400,
                transition: `color ${microDuration}s, border-color ${microDuration}s`,
              }}
            >
              {isDismissing ? 'Dismissing…' : isExpired ? 'Dismiss (expired)' : 'Dismiss'}
            </motion.button>
          </div>
        </>
      )}
    </motion.div>
  )
}
