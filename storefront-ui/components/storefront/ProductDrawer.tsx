'use client'
import { useEffect } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { PublicStore, LayoutGlobalConfig } from '@/types/schemas'
import { useCart } from '@/lib/cart'
import { readableOn } from '@/lib/color'

type Product = PublicStore['products'][number]
type DetailVariant = LayoutGlobalConfig['product_detail']

const EASE = [0.4, 0, 0.2, 1] as const

export function ProductDrawer({
  product, store, onClose, preview, variant = 'gallery-split',
}: {
  product: Product | null
  store: PublicStore
  onClose: () => void
  preview?: boolean
  variant?: DetailVariant
}) {
  const reduced = useReducedMotion()
  const add = useCart((s) => s.add)
  const setOpen = useCart((s) => s.setOpen)

  useEffect(() => {
    if (!product) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [product])

  const moreLikeThis = product
    ? store.products.filter((p) => p.id !== product.id && p.category === product.category).slice(0, 4)
    : []

  // Contrast-safe CTA colours. A brand whose accent is near-white (e.g. a B&W
  // logo → white accent on a light page) would render an invisible price and an
  // invisible "Add to cart". readableOn darkens the accent until it clears WCAG
  // on the page, then picks a label colour that reads on the resulting button.
  const accent = store.brand_token?.colors.accent ?? store.palette.accent
  const bg = store.brand_token?.colors.background ?? store.palette.background
  const ctaBg = readableOn(accent, bg)
  const ctaText = readableOn(bg, ctaBg)

  const Info = ({ p, big }: { p: Product; big?: boolean }) => (
    <div className="flex flex-col gap-4">
      <h2 className={big ? 'text-4xl md:text-5xl font-bold leading-tight' : 'text-2xl font-bold'}
          style={{ fontFamily: 'var(--s-display)' }}>
        {p.name}
      </h2>
      <p className={big ? 'text-2xl' : 'text-lg'} style={{ color: ctaBg }}>${p.price}</p>
      {p.description && (
        <p className="max-w-prose leading-relaxed" style={{ color: 'var(--s-text-muted)' }}>{p.description}</p>
      )}
      <button
        disabled={preview || !p.available}
        onClick={async () => { if (!preview) { await add(p.id, 1); setOpen(true) } }}
        className="mt-1 w-full py-3 rounded-full font-medium disabled:opacity-50"
        style={{ background: ctaBg, color: ctaText }}
      >
        {p.available ? 'Add to cart' : 'Sold out'}
      </button>
    </div>
  )

  const More = () =>
    moreLikeThis.length === 0 ? null : (
      <div>
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
    )

  const CloseBtn = () => (
    <button aria-label="Close" onClick={onClose}
            className="absolute top-4 right-4 z-10 w-9 h-9 rounded-full flex items-center justify-center"
            style={{ background: 'var(--s-surface)', color: 'var(--s-text)' }}>×</button>
  )

  // Panel variants slide from the right; minimal-centered fades+scales in the middle.
  const isCentered = variant === 'minimal-centered'
  const panelMotion = isCentered
    ? { initial: { opacity: 0, scale: reduced ? 1 : 0.96 }, animate: { opacity: 1, scale: 1 }, exit: { opacity: 0, scale: reduced ? 1 : 0.96 } }
    : { initial: { x: reduced ? 0 : '100%' }, animate: { x: 0 }, exit: { x: reduced ? 0 : '100%' } }

  const panelClass = isCentered
    ? 'relative m-auto w-[92vw] max-w-lg max-h-[88vh] overflow-y-auto rounded-2xl'
    : variant === 'editorial-stacked'
      ? 'absolute right-0 top-0 h-full w-full md:w-[820px] overflow-y-auto'
      : 'absolute right-0 top-0 h-full w-full md:w-[680px] overflow-y-auto'

  return (
    <AnimatePresence>
      {product && (
        <motion.div
          className={`fixed inset-0 z-40 ${isCentered ? 'flex p-4' : ''}`}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-black/55" onClick={onClose} aria-hidden />
          <motion.aside
            data-product-drawer data-testid="product-drawer" data-detail-variant={variant}
            className={panelClass}
            style={{ background: 'var(--s-bg)', color: 'var(--s-text)' }}
            {...panelMotion}
            transition={{ duration: reduced ? 0 : 0.3, ease: EASE }}
          >
            <CloseBtn />

            {variant === 'gallery-split' && (
              <>
                <div className="md:grid md:grid-cols-2">
                  <div className="w-full h-[40vh] md:h-full bg-cover bg-center"
                       style={{ background: product.image_url ? `url(${product.image_url}) center/cover` : 'var(--s-surface)' }} aria-hidden />
                  <div className="p-6 md:p-8"><Info p={product} /></div>
                </div>
                <div className="p-6 md:p-8"><More /></div>
              </>
            )}

            {variant === 'editorial-stacked' && (
              <div className="flex flex-col">
                <div className="w-full h-[52vh] bg-cover bg-center"
                     style={{ background: product.image_url ? `url(${product.image_url}) center/cover` : 'var(--s-surface)' }} aria-hidden />
                <div className="px-8 md:px-16 py-10 max-w-3xl mx-auto w-full"><Info p={product} big /></div>
                <div className="px-8 md:px-16 pb-12 max-w-3xl mx-auto w-full"><More /></div>
              </div>
            )}

            {variant === 'minimal-centered' && (
              <div className="p-6 md:p-8 flex flex-col items-center text-center gap-6">
                <div className="w-full aspect-square bg-cover bg-center rounded-xl"
                     style={{ background: product.image_url ? `url(${product.image_url}) center/cover` : 'var(--s-surface)' }} aria-hidden />
                <div className="w-full max-w-sm"><Info p={product} /></div>
              </div>
            )}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
