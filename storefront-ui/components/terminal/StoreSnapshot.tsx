'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { IconCart, IconTrend } from '@/components/icons'
import type { Merchant } from '@/types/schemas'

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

type Scenario = 'cart_abandon_surge' | 'velocity_spike'

interface StoreSnapshotProps {
  merchant: Merchant
  slug: string
  onSimulate: (scenario: Scenario) => void
  simulateState: 'idle' | 'sending' | 'done'
}

export function StoreSnapshot({ merchant, slug, onSimulate, simulateState }: StoreSnapshotProps) {
  const prefersReduced = useReducedMotion()

  return (
    <section className="flex flex-col gap-4">
      {/* Section header */}
      <p
        className="text-xs font-mono font-semibold uppercase"
        style={{ color: 'var(--color-accent)', letterSpacing: '0.1em' }}
      >
        Your Store
      </p>

      {/* Store card */}
      <div
        className="rounded-xl p-5"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        {/* Store name */}
        <h2
          className="text-2xl font-bold mb-1 leading-tight"
          style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
        >
          {merchant.store_name}
        </h2>

        {/* Slug link */}
        <Link
          href={`/s/${slug}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-mono"
          style={{ color: 'var(--color-text-muted)' }}
        >
          /s/{slug}
        </Link>

        {/* Status badge */}
        <div className="flex items-center gap-2 mt-3">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: merchant.is_live ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
          />
          <span
            className="text-xs font-mono"
            style={{ color: merchant.is_live ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
          >
            {merchant.is_live ? 'Live' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Simulate Activity — the demo's money button. Two scenarios so Qwen
          produces different decision types (abandon → recovery, spike → sale). */}
      <div className="flex flex-col gap-2">
        <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
          Simulate customer activity
        </span>

        {simulateState !== 'idle' ? (
          <div
            className="w-full py-3 rounded-xl text-sm font-semibold font-mono flex items-center justify-center gap-2"
            style={{
              border: `2px solid ${simulateState === 'done' ? '#4ade80' : 'var(--color-accent)'}`,
              color: simulateState === 'done' ? '#4ade80' : 'var(--color-accent)',
              background: 'var(--color-surface-2)',
            }}
          >
            {simulateState === 'sending' ? (
              <>
                <SpinnerIcon prefersReduced={prefersReduced} />
                ✦ Qwen is analyzing… (~15s)
              </>
            ) : (
              '✓ Decision ready — see the feed'
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2">
            <motion.button
              onClick={() => onSimulate('cart_abandon_surge')}
              whileTap={{ scale: 0.97 }} transition={{ duration: 0.15 }}
              className="w-full py-2.5 rounded-xl text-sm font-semibold font-mono cursor-pointer"
              style={{ border: '2px solid var(--color-accent)', color: 'var(--color-accent)', background: 'transparent' }}
            >
              <span className="inline-flex items-center justify-center gap-2"><IconCart size={16} /> Cart-abandon surge</span>
            </motion.button>
            <motion.button
              onClick={() => onSimulate('velocity_spike')}
              whileTap={{ scale: 0.97 }} transition={{ duration: 0.15 }}
              className="w-full py-2.5 rounded-xl text-sm font-semibold font-mono cursor-pointer"
              style={{ border: '2px solid var(--color-accent)', color: 'var(--color-accent)', background: 'transparent' }}
            >
              <span className="inline-flex items-center justify-center gap-2"><IconTrend size={16} /> Traffic spike</span>
            </motion.button>
          </div>
        )}
      </div>

      {/* View live store */}
      <Link
        href={`/s/${slug}`}
        target="_blank"
        rel="noopener noreferrer"
        className="block text-center text-sm font-mono py-2.5 rounded-xl"
        style={{
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-muted)',
          transition: 'color 0.15s, border-color 0.15s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--color-text)'
          e.currentTarget.style.borderColor = 'var(--color-text-muted)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--color-text-muted)'
          e.currentTarget.style.borderColor = 'var(--color-border)'
        }}
      >
        View Live Store →
      </Link>
    </section>
  )
}

function SpinnerIcon({ prefersReduced }: { prefersReduced: boolean }) {
  return (
    <motion.svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      animate={{ rotate: prefersReduced ? 0 : 360 }}
      transition={{ duration: 1, repeat: prefersReduced ? 0 : Infinity, ease: 'linear' }}
    >
      <path d="M21 12a9 9 0 11-6.219-8.56" />
    </motion.svg>
  )
}
