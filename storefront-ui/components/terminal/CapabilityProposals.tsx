'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import type { Capability } from '@/lib/api'

// ── Reduced-motion hook (mirrors DecisionFeed) ───────────────────────────────
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

/** Slugs ("mega-menu", "video_hero") → "mega menu", "video hero". Already-human
 *  labels pass through unchanged. */
function humanize(label: string): string {
  return (label || '').replace(/[-_]+/g, ' ').trim()
}

interface CapabilityProposalsProps {
  capabilities: Capability[]
}

/**
 * The "Qwen extends itself" moment. When the same point-and-edit intent the store
 * can't satisfy recurs, the backend flips that gap to status='proposed'. This
 * surfaces those proposals in the terminal — Qwen noticing its own limits and
 * proposing to grow. Pure/props-driven (like DecisionFeed) so the page owns the
 * fetch. Renders nothing until there's at least one proposal, so it only appears
 * when there's something to say.
 */
export function CapabilityProposals({ capabilities }: CapabilityProposalsProps) {
  const prefersReduced = useReducedMotion()
  const proposed = capabilities.filter((c) => c.status === 'proposed')
  if (proposed.length === 0) return null

  return (
    <motion.section
      data-testid="capability-proposals"
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
          ✦ Qwen proposes {proposed.length} new{' '}
          {proposed.length === 1 ? 'capability' : 'capabilities'}
        </span>
      </div>
      <p className="text-xs font-mono mb-3" style={{ color: 'var(--color-text-muted)' }}>
        Patterns it noticed in your edits that the store can&apos;t do yet.
      </p>

      <ul className="flex flex-col gap-2">
        {proposed.map((c, i) => (
          <motion.li
            key={c.capability}
            initial={prefersReduced ? false : { opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: prefersReduced ? 0 : 0.1 + i * 0.07 }}
            className="rounded-lg border px-3 py-2"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
          >
            <div className="flex items-center justify-between gap-2">
              <span
                className="text-sm font-medium capitalize"
                style={{ color: 'var(--color-text)' }}
              >
                {humanize(c.label)}
              </span>
              <span
                className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0"
                style={{
                  background: 'var(--color-accent-dim, rgba(110,231,183,0.12))',
                  color: 'var(--color-accent)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                requested {c.count}×
              </span>
            </div>
            {c.last_intent && (
              <p
                className="text-xs font-mono mt-1 truncate"
                style={{ color: 'var(--color-text-muted)' }}
                title={c.last_intent}
              >
                “{c.last_intent}”
              </p>
            )}
          </motion.li>
        ))}
      </ul>
    </motion.section>
  )
}
