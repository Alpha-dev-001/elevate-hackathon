'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconCart } from '@/components/icons'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import type { PublicStore, PublicProduct } from '@/types/schemas'
import { storeThemeVars, useStoreFonts } from '@/lib/storeTheme'
import { useCart } from '@/lib/cart'
import { sameCategory } from '@/lib/category'
import { ProductGrid } from './ProductGrid'
import { Cart } from './Cart'

/**
 * Themed product detail. Reuses the public store payload (small catalogs) to
 * render the product with its effective price/promo, a quantity add-to-cart, and
 * related items by category — all in the store's own brand.
 */
export function ProductDetail({ slug, productId }: { slug: string; productId: string }) {
  const [store, setStore] = useState<PublicStore | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'notfound' | 'error'>('loading')
  const [qty, setQty] = useState(1)
  const [imgFailed, setImgFailed] = useState(false)

  const initCart = useCart((s) => s.init)
  const add = useCart((s) => s.add)
  const busy = useCart((s) => s.busy)
  const openCart = useCart((s) => s.setOpen)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)

  useStoreFonts(store)

  useEffect(() => {
    api
      .getStore(slug)
      .then((s) => { setStore(s); setStatus('ok') })
      .catch((e) => setStatus(e instanceof ApiError && e.status === 404 ? 'notfound' : 'error'))
  }, [slug])

  useEffect(() => { initCart(slug) }, [slug, initCart])

  const product: PublicProduct | undefined = useMemo(
    () => store?.products.find((p) => p.id === productId),
    [store, productId],
  )

  const related = useMemo(
    () =>
      (store?.products ?? [])
        .filter((p) => p.id !== productId && product?.category && sameCategory(p.category, product.category))
        .slice(0, 3),
    [store, product, productId],
  )

  if (status === 'loading') return <Center>Opening…</Center>
  if (status === 'notfound' || (status === 'ok' && !product)) return <Center>This product isn’t available.</Center>
  if (status === 'error' || !store || !product) return <Center>Couldn’t load this product.</Center>

  const themeVars = storeThemeVars(store)
  const discounted = product.compare_at_price != null

  return (
    <main style={themeVars}>
      <button
        onClick={() => openCart(true)}
        aria-label={`Open cart (${cartCount} items)`}
        className="fixed top-4 right-4 z-30 rounded-full w-12 h-12 flex items-center justify-center shadow-lg"
        style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
      >
        <IconCart size={20} />
        {cartCount > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full text-[11px] font-bold flex items-center justify-center"
            style={{ background: 'var(--s-bg)', color: 'var(--s-text)', border: '1px solid var(--s-accent)' }}
          >
            {cartCount}
          </span>
        )}
      </button>

      <Cart />

      <div className="max-w-4xl mx-auto px-5 py-10">
        <Link href={`/s/${slug}`} className="text-sm font-mono mb-6 inline-block hover:underline" style={{ color: 'var(--s-text-muted)' }}>
          ← {store.store_name}
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
          className="grid grid-cols-1 md:grid-cols-2 gap-8"
        >
          <div
            className="aspect-square rounded-2xl flex items-center justify-center overflow-hidden relative"
            style={{ background: 'color-mix(in srgb, var(--s-primary) 16%, var(--s-bg))' }}
          >
            {product.image_url && !imgFailed ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={product.image_url}
                alt={product.name}
                className="w-full h-full object-contain"
                onError={() => setImgFailed(true)}
              />
            ) : (
              <div className="w-20 h-20 [&>svg]:w-full [&>svg]:h-full" style={{ opacity: 0.2 }} dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }} />
            )}
            {product.promo_label && (
              <span className="absolute top-3 left-3 text-xs font-semibold px-2.5 py-1 rounded-full" style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
                {product.promo_label}
              </span>
            )}
          </div>

          <div className="flex flex-col gap-4">
            {product.category && (
              <span className="text-xs font-mono uppercase tracking-wide" style={{ color: 'var(--s-text-subtle)' }}>
                {product.category}
              </span>
            )}
            <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: 'var(--s-display)' }}>
              {product.name}
            </h1>
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-semibold" style={{ color: 'var(--s-accent-text)' }}>
                ${product.price.toFixed(2)}
              </span>
              {discounted && (
                <span className="text-lg line-through" style={{ color: 'var(--s-text-subtle)' }}>
                  ${product.compare_at_price!.toFixed(2)}
                </span>
              )}
            </div>
            {product.description && (
              <p className="text-sm leading-relaxed" style={{ color: 'var(--s-text-muted)' }}>
                {product.description}
              </p>
            )}

            {product.available ? (
              <div className="flex items-center gap-3 mt-2">
                <div className="flex items-center gap-2">
                  <StepBtn onClick={() => setQty((q) => Math.max(1, q - 1))}>−</StepBtn>
                  <span className="w-6 text-center">{qty}</span>
                  <StepBtn onClick={() => setQty((q) => q + 1)}>+</StepBtn>
                </div>
                <button
                  disabled={busy}
                  onClick={() => add(product.id, qty)}
                  className="flex-1 rounded-md py-3 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                  style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
                >
                  Add to cart
                </button>
              </div>
            ) : (
              <p className="text-sm font-mono mt-2" style={{ color: 'var(--s-text-subtle)' }}>Sold out</p>
            )}
          </div>
        </motion.div>

        {related.length > 0 && (
          <section className="mt-16">
            <h2 className="text-lg font-semibold mb-5" style={{ fontFamily: 'var(--s-display)' }}>More like this</h2>
            <ProductGrid products={related} logoMark={store.icons.logo_mark} slug={slug} />
          </section>
        )}
      </div>
    </main>
  )
}

function StepBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-8 h-8 rounded flex items-center justify-center"
      style={{ border: '1px solid color-mix(in srgb, var(--s-text) 20%, transparent)' }}
    >
      {children}
    </button>
  )
}

function Center({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen flex items-center justify-center bg-bg">
      <p className="text-muted font-mono text-sm">{children}</p>
    </main>
  )
}
