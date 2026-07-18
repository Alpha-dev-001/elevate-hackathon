'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { IconSpark } from '@/components/icons'
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

type ReviewState = 'idle' | 'sending' | 'found' | 'clean' | 'error'

interface StoreSnapshotProps {
  merchant: Merchant
  slug: string
  onReview: () => void
  reviewState: ReviewState
}

export function StoreSnapshot({ merchant, slug, onReview, reviewState }: StoreSnapshotProps) {
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

      {/* Proactive review — Qwen looks at the catalog without waiting for an
          anomaly (views vs. real orders). Distinct from Simulate above:
          this reads real store data, it doesn't fake customer events. */}
      <div className="flex flex-col gap-2">
        <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
          Proactive review
        </span>

        {reviewState !== 'idle' ? (
          <div
            className="w-full py-3 rounded-xl text-sm font-semibold font-mono flex items-center justify-center gap-2 text-center"
            style={{
              border: `2px solid ${reviewState === 'found' ? '#4ade80' : reviewState === 'error' ? 'var(--color-danger)' : reviewState === 'clean' ? 'var(--color-border)' : 'var(--color-accent)'}`,
              color: reviewState === 'found' ? '#4ade80' : reviewState === 'error' ? 'var(--color-danger)' : reviewState === 'clean' ? 'var(--color-text-muted)' : 'var(--color-accent)',
              background: 'var(--color-surface-2)',
            }}
          >
            {reviewState === 'sending' ? (
              <>
                <SpinnerIcon prefersReduced={prefersReduced} />
                ✦ Qwen is reviewing the catalog…
              </>
            ) : reviewState === 'found' ? (
              '✓ Decision ready — see the feed'
            ) : reviewState === 'error' ? (
              '⚠ Review failed — try again'
            ) : (
              '✓ Catalog looks healthy — nothing to flag'
            )}
          </div>
        ) : (
          <motion.button
            onClick={onReview}
            whileTap={{ scale: 0.97 }} transition={{ duration: 0.15 }}
            className="w-full py-2.5 rounded-xl text-sm font-semibold font-mono cursor-pointer"
            style={{ border: '2px solid var(--color-accent)', color: 'var(--color-accent)', background: 'transparent' }}
          >
            <span className="inline-flex items-center justify-center gap-2"><IconSpark size={16} /> Review store now</span>
          </motion.button>
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
