'use client'
import { useState } from 'react'
import type { SectionProps } from '@/lib/dslRegistry'
import { ProductImage } from '@/components/storefront/ProductImage'

export function SingleSpotlightGrid({ store, onOpenProduct }: SectionProps) {
  const [idx, setIdx] = useState(0)
  const products = store.products
  if (products.length === 0) return <section data-grid="single-spotlight" className="py-20" />
  const p = products[idx % products.length]
  const c = store.brand_token!.colors
  return (
    <section data-grid="single-spotlight" className="px-4 md:px-8 py-16 grid md:grid-cols-2 gap-8 items-center">
      <button data-product onClick={() => onOpenProduct?.(p.id)}
              className="block w-full aspect-[4/5] overflow-hidden" style={{ background: c.surface }}>
        <ProductImage src={p.image_url} alt={p.name} initial={p.name} className="w-full h-full object-cover" />
      </button>
      <div className="flex flex-col gap-4" style={{ color: c.text }}>
        <h3 className="text-3xl font-bold" style={{ fontFamily: 'var(--s-display)' }}>{p.name}</h3>
        <div className="flex items-baseline gap-3 flex-wrap">
          <p className="text-lg" style={{ color: 'var(--s-cta)' }}>${p.price.toFixed(2)}</p>
          {p.compare_at_price != null && (
            <span className="text-base line-through" style={{ color: 'var(--s-text-subtle)' }}>
              ${p.compare_at_price.toFixed(2)}
            </span>
          )}
          {p.promo_label && (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                  style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
              {p.promo_label}
            </span>
          )}
        </div>
        <p style={{ color: c.text_muted }}>{p.description}</p>
        <div className="flex gap-3 mt-2">
          <button aria-label="Previous" onClick={() => setIdx((i) => (i - 1 + products.length) % products.length)}
                  className="px-4 py-2 rounded-full" style={{ border: `1px solid ${c.text_muted}` }}>←</button>
          <button aria-label="Next" onClick={() => setIdx((i) => (i + 1) % products.length)}
                  className="px-4 py-2 rounded-full" style={{ border: `1px solid ${c.text_muted}` }}>→</button>
        </div>
      </div>
    </section>
  )
}
