'use client'

import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { AgentAction } from '@/types/schemas'
import { OptionCard } from './OptionCard'

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

interface DecisionFeedProps {
  actions: AgentAction[]
  slug: string
  onApproveAction: (id: string) => void
  onDismissAction: (id: string) => void
  onClamped: (msg: string) => void
}

export function DecisionFeed({ actions, onApproveAction, onDismissAction, onClamped }: DecisionFeedProps) {
  const prefersReduced = useReducedMotion()

  return (
    <section>
      {/* Section header */}
      <p
        className="text-xs font-mono font-semibold uppercase mb-4"
        style={{ color: 'var(--color-accent)', letterSpacing: '0.1em' }}
      >
        AI Suggestions
        {actions.length > 0 && (
          <span
            className="ml-2 px-1.5 py-0.5 rounded text-xs"
            style={{
              background: 'var(--color-accent-dim)',
              color: 'var(--color-accent)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {actions.length}
          </span>
        )}
      </p>

      <AnimatePresence mode="popLayout">
        {actions.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="flex flex-col items-center justify-center py-16 text-center"
          >
            {/* Breathing pulse */}
            <motion.p
              animate={{ opacity: prefersReduced ? 0.5 : [0.3, 0.8, 0.3] }}
              transition={{ duration: 3, repeat: prefersReduced ? 0 : Infinity, ease: 'easeInOut' }}
              className="text-base font-mono mb-3"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Watching the store…
            </motion.p>

            {/* Ambient dot */}
            <motion.div
              animate={{ scale: prefersReduced ? 1 : [1, 1.3, 1], opacity: prefersReduced ? 0.5 : [0.4, 0.9, 0.4] }}
              transition={{ duration: 3, repeat: prefersReduced ? 0 : Infinity, ease: 'easeInOut' }}
              className="w-1.5 h-1.5 rounded-full mb-4"
              style={{ background: 'var(--color-accent)' }}
            />

            <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
              No suggestions yet. Simulate activity to generate one.
            </p>
          </motion.div>
        ) : (
          <div className="flex flex-col gap-4">
            {actions.map((action, i) => (
              <AnimatePresence key={action.id} mode="popLayout">
                <OptionCard
                  action={action}
                  onApprove={onApproveAction}
                  onDismiss={onDismissAction}
                  onClamped={onClamped}
                  delay={i * 0.07}
                />
              </AnimatePresence>
            ))}
          </div>
        )}
      </AnimatePresence>
    </section>
  )
}
