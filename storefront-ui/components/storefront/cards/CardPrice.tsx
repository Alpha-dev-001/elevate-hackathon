'use client'
import type { PublicStore } from '@/types/schemas'

type P = Pick<PublicStore['products'][number], 'price' | 'compare_at_price'>

/**
 * Price display for the DSL grid cards. When a promo is active the store payload
 * carries `compare_at_price` (the original) — this renders the struck original and
 * a "-N%" chip next to the live price, so a flash sale actually shows on the grid
 * and not only in the top banner. No discount → just the price, unchanged.
 */
export function CardPrice({ product }: { product: P }) {
  const c = product.compare_at_price
  const off = c && c > product.price ? Math.round((1 - product.price / c) * 100) : 0
  if (off <= 0) return <>${product.price}</>
  return (
    <>
      ${product.price}
      <span className="line-through ml-1.5" style={{ color: 'var(--s-text-muted)', fontSize: '0.85em' }}>
        ${c}
      </span>
      <span
        className="ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold align-middle whitespace-nowrap"
        style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
      >
        -{off}%
      </span>
    </>
  )
}
