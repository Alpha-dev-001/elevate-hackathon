'use client'
import { useEffect } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { PublicStore } from '@/types/schemas'
import { useCart } from '@/lib/cart'

type Product = PublicStore['products'][number]

export function ProductDrawer({
  product, store, onClose, preview,
}: {
  product: Product | null
  store: PublicStore
  onClose: () => void
  preview?: boolean
}) {
  const reduced = useReducedMotion()
  const add = useCart((s) => s.add)
  const setOpen = useCart((s) => s.setOpen)

  // Lock body scroll while open.
  useEffect(() => {
    if (!product) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [product])

  const moreLikeThis = product
    ? store.products.filter((p) => p.id !== product.id && p.category === product.category).slice(0, 4)
    : []

  return (
    <AnimatePresence>
      {product && (
        <motion.div
          className="fixed inset-0 z-40"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
          <motion.aside
            data-product-drawer data-testid="product-drawer"
            className="absolute right-0 top-0 h-full w-full md:w-[680px] overflow-y-auto"
            style={{ background: 'var(--s-bg)', color: 'var(--s-text)' }}
            initial={{ x: reduced ? 0 : '100%' }}
            animate={{ x: 0 }}
            exit={{ x: reduced ? 0 : '100%' }}
            transition={{ duration: reduced ? 0 : 0.28, ease: [0.4, 0, 0.2, 1] }}
          >
            <button aria-label="Close" onClick={onClose}
                    className="absolute top-4 right-4 z-10 w-9 h-9 rounded-full flex items-center justify-center"
                    style={{ background: 'var(--s-surface)', color: 'var(--s-text)' }}>×</button>

            <div className="md:grid md:grid-cols-2">
              <div className="w-full h-[40vh] md:h-full bg-cover bg-center"
                   style={{ background: product.image_url ? `url(${product.image_url}) center/cover` : 'var(--s-surface)' }}
                   aria-hidden />
              <div className="flex flex-col gap-4 p-6 md:p-8">
                <h2 className="text-2xl font-bold" style={{ fontFamily: 'var(--s-display)' }}>{product.name}</h2>
                <p className="text-lg" style={{ color: 'var(--s-accent)' }}>${product.price}</p>
                {product.description && <p style={{ color: 'var(--s-text-muted)' }}>{product.description}</p>}
                <button
                  disabled={preview || !product.available}
                  onClick={async () => { await add(product.id, 1); setOpen(true) }}
                  className="mt-2 w-full py-3 rounded-full font-medium disabled:opacity-50"
                  style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}>
                  {product.available ? 'Add to cart' : 'Sold out'}
                </button>
              </div>
            </div>

            {moreLikeThis.length > 0 && (
              <div className="p-6 md:p-8">
                <h3 className="text-sm uppercase tracking-widest mb-3" style={{ color: 'var(--s-text-muted)' }}>More like this</h3>
                <div className="flex gap-3 overflow-x-auto">
                  {moreLikeThis.map((p) => (
                    <div key={p.id} className="shrink-0 w-[140px]">
                      <div className="w-full aspect-[3/4] bg-cover bg-center"
                           style={{ background: p.image_url ? `url(${p.image_url}) center/cover` : 'var(--s-surface)' }} aria-hidden />
                      <span className="block mt-1 text-xs" style={{ color: 'var(--s-text)' }}>{p.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
