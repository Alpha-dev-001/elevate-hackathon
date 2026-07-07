'use client'

import { useMemo, useState } from 'react'
import { IconCart } from '@/components/icons'
import { motion, useReducedMotion } from 'framer-motion'
import type { PublicStore } from '@/types/schemas'
import { resolveTheme } from '@/lib/storeTheme'
import { ProductGrid } from './ProductGrid'
import { Cart } from './Cart'
import { useCart } from '@/lib/cart'

/**
 * The no-brand_token / no-DSL path. Ported verbatim from the original
 * LayoutRouter fallback so pre-Sprint-3 stores look unchanged. Self-contained:
 * computes its own theme, owns filter state, renders cart chrome.
 */
export function FallbackStorefront({ store, slug }: { store: PublicStore; slug: string }) {
  const prefersReduced = useReducedMotion()
  const [query, setQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const openCart = useCart((s) => s.setOpen)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return store.products.filter((p) => {
      if (activeCategory && p.category !== activeCategory) return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        (p.description?.toLowerCase().includes(q) ?? false) ||
        (p.category?.toLowerCase().includes(q) ?? false)
      )
    })
  }, [store.products, query, activeCategory])

  const theme = resolveTheme(store)

  return (
    <main data-testid="fallback-storefront" style={theme.cssVars}>
      {store.promos.length > 0 && (
        <div className="w-full text-center py-2.5 text-sm font-medium"
             style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
          {store.promos[0].label}
        </div>
      )}

      <button
        onClick={() => openCart(true)}
        aria-label={`Open cart (${cartCount} items)`}
        className="fixed top-4 right-4 z-30 rounded-full w-12 h-12 flex items-center justify-center shadow-lg hover:opacity-90 transition-opacity"
        style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
      >
        <IconCart size={20} />
        {cartCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full text-[11px] font-bold flex items-center justify-center"
                style={{ background: 'var(--s-bg)', color: 'var(--s-text)', border: '1px solid var(--s-accent)' }}>
            {cartCount}
          </span>
        )}
      </button>
      <Cart />

      <div className="max-w-5xl mx-auto px-5 py-12">
        <motion.header
          initial={{ opacity: 0, y: prefersReduced ? 0 : 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: prefersReduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
          className="flex flex-col items-center text-center gap-3 mb-12"
        >
          <div className="w-16 h-16 [&>svg]:w-full [&>svg]:h-full" role="img"
               aria-label={`${store.store_name} logo`}
               dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }} />
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight break-words max-w-2xl [text-wrap:balance]"
              style={{ fontFamily: 'var(--s-display)' }}>
            {store.store_name}
          </h1>
          <p className="text-base" style={{ color: 'var(--s-accent-text)' }}>{store.tagline}</p>
        </motion.header>

        {store.products.length > 0 && (
          <div className="mb-8 flex flex-col gap-4">
            <input
              type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search products…"
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none"
              style={{
                background: 'color-mix(in srgb, var(--s-text) 5%, var(--s-bg))',
                color: 'var(--s-text)',
                border: '1px solid color-mix(in srgb, var(--s-text) 15%, transparent)',
              }}
            />
            {store.categories.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <Chip label="All" active={activeCategory === null} onClick={() => setActiveCategory(null)} />
                {store.categories.map((c) => (
                  <Chip key={c} label={c} active={activeCategory === c} onClick={() => setActiveCategory(c)} />
                ))}
              </div>
            )}
          </div>
        )}

        <ProductGrid
          products={filtered}
          logoMark={store.icons.logo_mark}
          slug={slug}
          emptyLabel={store.products.length === 0 ? 'Preparing the shelves' : 'Nothing matches'}
          emptySub={store.products.length === 0 ? 'New pieces are on their way.' : 'Try a different search or category.'}
        />

        <footer className="text-center mt-16 text-xs font-mono" style={{ color: 'var(--s-text-subtle)' }}>
          Powered by Elevate
        </footer>
      </div>
    </main>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-xs font-mono uppercase tracking-wide px-3 py-1.5 rounded-full transition-colors"
      style={
        active
          ? { background: 'var(--s-cta)', color: 'var(--s-on-cta)' }
          : {
              background: 'transparent',
              color: 'var(--s-text-muted)',
              border: '1px solid color-mix(in srgb, var(--s-text) 18%, transparent)',
            }
      }
    >
      {label}
    </button>
  )
}
