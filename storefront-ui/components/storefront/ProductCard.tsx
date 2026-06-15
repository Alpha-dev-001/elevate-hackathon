'use client'

import { motion } from 'framer-motion'
import type { PublicProduct } from '@/types/schemas'

/**
 * A single product tile. Colors come from CSS vars set by the Storefront
 * wrapper (--s-bg / --s-text / --s-accent / --s-primary) so every store is
 * themed by its own generated brand, not the Elevate admin palette.
 */
export function ProductCard({ product, index }: { product: PublicProduct; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      className="rounded-xl overflow-hidden flex flex-col"
      style={{
        border: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)',
        background: 'color-mix(in srgb, var(--s-text) 3%, var(--s-bg))',
      }}
    >
      <div
        className="aspect-square w-full flex items-center justify-center relative"
        style={{ background: 'color-mix(in srgb, var(--s-primary) 16%, var(--s-bg))' }}
      >
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />
        ) : (
          <span
            className="text-4xl font-bold"
            style={{ fontFamily: 'var(--s-display)', color: 'var(--s-accent)' }}
          >
            {product.name.slice(0, 1).toUpperCase()}
          </span>
        )}
        {!product.available && (
          <span
            className="absolute top-2 right-2 text-[10px] font-mono px-2 py-0.5 rounded-full"
            style={{ background: 'var(--s-bg)', color: 'var(--s-text)', opacity: 0.85 }}
          >
            Sold out
          </span>
        )}
      </div>

      <div className="p-4 flex flex-col gap-1.5">
        <div className="flex justify-between items-start gap-2">
          <h3 className="font-semibold leading-tight" style={{ fontFamily: 'var(--s-display)' }}>
            {product.name}
          </h3>
          <span className="font-semibold shrink-0" style={{ color: 'var(--s-accent-text)' }}>
            ${product.price}
          </span>
        </div>
        {product.category && (
          <span className="text-[11px] font-mono uppercase tracking-wide" style={{ opacity: 0.5 }}>
            {product.category}
          </span>
        )}
        {product.description && (
          <p className="text-sm leading-relaxed mt-0.5" style={{ opacity: 0.72 }}>
            {product.description}
          </p>
        )}
      </div>
    </motion.div>
  )
}
