'use client'

import { motion } from 'framer-motion'
import type { PublicProduct } from '@/types/schemas'
import { ProductCard } from './ProductCard'

/**
 * The product grid, mobile-first (1 col → 2 → 3). When there are no products,
 * shows a branded "preparing the shelves" state using the store's own logo
 * mark and palette — intentional, not broken.
 */
export function ProductGrid({
  products,
  logoMark,
}: {
  products: PublicProduct[]
  logoMark: string
}) {
  if (products.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center justify-center text-center py-24 gap-5"
      >
        <motion.div
          className="w-20 h-20 [&>svg]:w-full [&>svg]:h-full opacity-90"
          animate={{ scale: [1, 1.06, 1] }}
          transition={{ duration: 3, repeat: Infinity, ease: [0.4, 0, 0.2, 1] }}
          dangerouslySetInnerHTML={{ __html: logoMark }}
        />
        <div>
          <p className="text-lg" style={{ fontFamily: 'var(--s-display)' }}>
            Preparing the shelves
          </p>
          <p className="text-sm mt-1" style={{ opacity: 0.6 }}>
            New pieces are on their way.
          </p>
        </div>
      </motion.div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {products.map((p, i) => (
        <ProductCard key={p.id} product={p} index={i} />
      ))}
    </div>
  )
}
