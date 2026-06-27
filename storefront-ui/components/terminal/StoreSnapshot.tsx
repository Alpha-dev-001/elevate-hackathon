'use client'

import { motion } from 'framer-motion'
import Link from 'next/link'
import type { Merchant } from '@/types/schemas'

interface StoreSnapshotProps {
  merchant: Merchant
  slug: string
  onSimulate: () => void
  simulateState: 'idle' | 'sending' | 'done'
}

export function StoreSnapshot({ merchant, slug, onSimulate, simulateState }: StoreSnapshotProps) {
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

      {/* Simulate Activity button — the demo's money button */}
      <motion.button
        onClick={onSimulate}
        disabled={simulateState !== 'idle'}
        whileTap={{ scale: simulateState === 'idle' ? 0.97 : 1 }}
        transition={{ duration: 0.15 }}
        className="w-full py-3 rounded-xl text-sm font-semibold font-mono cursor-pointer disabled:cursor-not-allowed"
        style={{
          border: `2px solid ${simulateState === 'done' ? '#4ade80' : 'var(--color-accent)'}`,
          color:
            simulateState === 'idle'
              ? 'var(--color-accent)'
              : simulateState === 'sending'
              ? 'var(--color-text-muted)'
              : '#4ade80',
          background:
            simulateState === 'idle'
              ? 'transparent'
              : 'var(--color-surface-2)',
          transition: 'color 0.2s, border-color 0.2s, background 0.2s',
        }}
      >
        {simulateState === 'idle' && '▶ Simulate Activity'}
        {simulateState === 'sending' && (
          <span className="flex items-center justify-center gap-2">
            <SpinnerIcon />
            Sending events…
          </span>
        )}
        {simulateState === 'done' && '✓ Done'}
      </motion.button>

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

function SpinnerIcon() {
  return (
    <motion.svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
    >
      <path d="M21 12a9 9 0 11-6.219-8.56" />
    </motion.svg>
  )
}
