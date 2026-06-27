'use client'

import { motion, useReducedMotion } from 'framer-motion'
import type { PublicProduct, BrandToken } from '@/types/schemas'
import { ProductCard } from './ProductCard'

/**
 * Renders the product catalog in one of three grid variants:
 *   2col-featured — first product spans 2 cols (editorial hero card),
 *                    rest in a uniform 2–3 col grid below.
 *   3col-equal    — uniform 3-column grid (default).
 *   masonry       — CSS columns, variable-height cards break naturally.
 *
 * When products is empty, shows a branded "preparing the shelves" state
 * using the store's logo mark — intentional, not broken.
 *
 * All new props (gridVariant, cardStyle, brandToken) default gracefully so
 * existing callers (ProductDetail) continue to work without changes.
 */
export function ProductGrid({
  products,
  logoMark,
  slug,
  emptyLabel = 'Preparing the shelves',
  emptySub = 'New pieces are on their way.',
  gridVariant = '3col-equal',
  cardStyle = 'elevated',
  brandToken,
}: {
  products: PublicProduct[]
  logoMark: string
  slug?: string
  emptyLabel?: string
  emptySub?: string
  gridVariant?: '2col-featured' | '3col-equal' | 'masonry'
  cardStyle?: 'borderless' | 'outlined' | 'elevated' | 'colored-bg'
  brandToken?: BrandToken | null
}) {
  const prefersReduced = useReducedMotion()

  if (products.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: prefersReduced ? 0 : 0.6 }}
        className="flex flex-col items-center justify-center text-center py-24 gap-5"
      >
        <motion.div
          className="w-20 h-20 [&>svg]:w-full [&>svg]:h-full opacity-90"
          role="img"
          aria-label="Store logo"
          animate={prefersReduced ? {} : { scale: [1, 1.06, 1] }}
          transition={{ duration: 3, repeat: prefersReduced ? 0 : Infinity, ease: [0.4, 0, 0.2, 1] }}
          dangerouslySetInnerHTML={{ __html: logoMark }}
        />
        <div>
          <p className="text-lg" style={{ fontFamily: 'var(--s-display)' }}>
            {emptyLabel}
          </p>
          <p className="text-sm mt-1" style={{ color: 'var(--s-text-muted)' }}>
            {emptySub}
          </p>
        </div>
      </motion.div>
    )
  }

  // ── 2col-featured: first product hero (spans full width on md+) ────────────
  if (gridVariant === '2col-featured') {
    const [featured, ...rest] = products
    return (
      <div>
        {featured && (
          <div className="mb-4">
            <ProductCard
              product={featured}
              index={0}
              logoMark={logoMark}
              slug={slug}
              cardStyle={cardStyle}
              featured
              brandToken={brandToken}
            />
          </div>
        )}
        {rest.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {rest.map((p, i) => (
              <ProductCard
                key={p.id}
                product={p}
                index={i + 1}
                logoMark={logoMark}
                slug={slug}
                cardStyle={cardStyle}
                brandToken={brandToken}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  // ── masonry: variable-height cards via CSS columns ─────────────────────────
  if (gridVariant === 'masonry') {
    return (
      <div className="columns-1 sm:columns-2 lg:columns-3 gap-4">
        {products.map((p, i) => (
          <div key={p.id} className="break-inside-avoid mb-4">
            <ProductCard
              product={p}
              index={i}
              logoMark={logoMark}
              slug={slug}
              cardStyle={cardStyle}
              brandToken={brandToken}
            />
          </div>
        ))}
      </div>
    )
  }

  // ── 3col-equal (default) ───────────────────────────────────────────────────
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {products.map((p, i) => (
        <ProductCard
          key={p.id}
          product={p}
          index={i}
          logoMark={logoMark}
          slug={slug}
          cardStyle={cardStyle}
          brandToken={brandToken}
        />
      ))}
    </div>
  )
}
