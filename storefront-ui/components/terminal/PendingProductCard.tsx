'use client'

import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { ProductImage } from '@/components/storefront/ProductImage'
import type { Product } from '@/types/schemas'

/**
 * A Qwen-vision-identified product awaiting merchant approval, rendered as
 * a card in the terminal's live feed — same approve/discard actions as the
 * /products page's own pending list (GET /products/pending,
 * POST /products/{id}/approve, DELETE /products/{id}), just also surfaced
 * where the merchant is actually watching after publish, not only during
 * onboarding.
 */
export function PendingProductCard({
  product,
  onApproved,
  onDiscarded,
}: {
  product: Product
  onApproved: (p: Product) => void
  onDiscarded: (id: string) => void
}) {
  const approve = async () => {
    try {
      const approved = await api.approveProduct(product.id)
      onApproved(approved)
    } catch {
      // leave the card in place — merchant can retry
    }
  }

  const discard = async () => {
    try {
      await api.deleteProduct(product.id)
      onDiscarded(product.id)
    } catch {
      // leave the card in place — merchant can retry
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -40, transition: { duration: 0.25 } }}
      transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
      className="rounded-lg p-4 flex gap-4 items-start"
      style={{
        background: 'var(--color-surface-2)',
        border: '1px solid color-mix(in srgb, var(--color-accent) 30%, var(--color-border))',
      }}
    >
      <div className="w-14 h-14 rounded-md overflow-hidden bg-surface-2 shrink-0">
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold truncate" style={{ color: 'var(--color-text)' }}>{product.name}</p>
          <span className="font-mono text-sm" style={{ color: 'var(--color-accent)' }}>${product.price}</span>
          <span
            className="text-[10px] font-mono rounded-full px-1.5 py-0.5"
            style={{ color: 'var(--color-text-muted)', border: '1px solid var(--color-border)' }}
          >
            from photo
          </span>
        </div>
        {product.description && (
          <p className="text-sm mt-1 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>{product.description}</p>
        )}
        <div className="flex gap-2 mt-3">
          <button
            onClick={approve}
            className="font-semibold rounded-md py-1.5 px-4 text-xs hover:opacity-90 transition-opacity"
            style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}
          >
            Approve
          </button>
          <button
            onClick={discard}
            className="rounded-md py-1.5 px-3 text-xs transition-colors"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Discard
          </button>
        </div>
      </div>
    </motion.div>
  )
}
