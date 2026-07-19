'use client'

import { useMemo, useState } from 'react'
import { IconCart } from '@/components/icons'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { PublicProduct, PublicStore } from '@/types/schemas'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { EditorialLayout } from './layouts/EditorialLayout'
import { BoldGridLayout } from './layouts/BoldGridLayout'
import { MinimalDarkLayout } from './layouts/MinimalDarkLayout'
import { WarmCraftLayout } from './layouts/WarmCraftLayout'
import { ProductGrid } from './ProductGrid'
import { BrandLogo } from './BrandLogo'
import { Cart } from './Cart'
import { useCart } from '@/lib/cart'
import { readableOn } from '@/lib/color'
import { sameCategory } from '@/lib/category'

/**
 * Smart layout switcher. Owns the filter state so Storefront.tsx stays lean.
 *
 * When brand_token is present:
 *   - Resolves the full ResolvedTheme (CSS vars + layout config)
 *   - Wraps with StoreShell for CSS var injection
 *   - Animates layout transitions with AnimatePresence
 *   - Routes to one of 4 layout variants
 *
 * When brand_token is null:
 *   - Falls back to the generic default layout (original Storefront appearance)
 *   - Uses storeThemeVars for CSS vars
 *
 * Both paths include the floating cart button and Cart side-panel.
 */
export function LayoutRouter({ store, slug }: { store: PublicStore; slug: string }) {
  const prefersReduced = useReducedMotion()
  const [query, setQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  const openCart = useCart((s) => s.setOpen)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)

  const filtered = useMemo(() => {
    const items = store.products
    const q = query.trim().toLowerCase()
    return items.filter((p) => {
      if (activeCategory && !sameCategory(p.category, activeCategory)) return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        (p.description?.toLowerCase().includes(q) ?? false) ||
        (p.category?.toLowerCase().includes(q) ?? false)
      )
    })
  }, [store.products, query, activeCategory])

  const theme = resolveTheme(store)
  const bt = store.brand_token ?? null

  // Promo banner (shared across all layouts). Each product prices itself
  // independently (see best_active_promo in store.py) — several can be on
  // sale at once. Naming just promos[0] here would misrepresent the others
  // as either absent or as if they shared its label, so a single active promo
  // is named directly and multiple collapse to an accurate count instead of
  // picking one arbitrarily.
  const hasPromo = store.promos.length > 0
  const promoText =
    store.promos.length === 1
      ? store.promos[0].label
      : `${store.promos.length} items on sale right now`
  const promoBar = hasPromo ? (
    <div
      className="w-full text-center py-2.5 text-sm font-medium"
      style={{
        background: bt ? bt.colors.accent : store.palette.accent,
        color: bt
          ? readableOn(bt.colors.accent, bt.colors.background)
          : readableOn(store.palette.accent, store.palette.background),
      }}
    >
      {promoText}
    </div>
  ) : null

  // Floating cart button (shared — colors adapt to theme)
  const cartBtn = (
    <button
      onClick={() => openCart(true)}
      aria-label={`Open cart (${cartCount} item${cartCount === 1 ? '' : 's'})`}
      className="fixed top-4 right-4 z-30 rounded-full w-12 h-12 flex items-center justify-center shadow-lg hover:opacity-90 transition-opacity"
      style={{
        background: 'var(--s-cta)',
        color: 'var(--s-on-cta)',
      }}
    >
      <IconCart size={20} />
      {cartCount > 0 && (
        <span
          className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full text-[11px] font-bold flex items-center justify-center"
          style={{
            background: 'var(--s-bg)',
            color: 'var(--s-text)',
            border: '1px solid var(--s-accent)',
          }}
        >
          {cartCount}
        </span>
      )}
    </button>
  )

  const layoutKey = bt?.layout.style ?? 'default'

  const layoutProps = {
    store,
    slug,
    filtered,
    query,
    setQuery,
    activeCategory,
    setActiveCategory,
  }

  // ── Branded path ──────────────────────────────────────────────────────────
  if (bt) {
    return (
      <StoreShell brandToken={bt} cssVars={theme.cssVars}>
        {promoBar}
        {cartBtn}
        <Cart />

        <AnimatePresence mode="wait">
          <motion.div
            key={layoutKey}
            initial={{ opacity: 0, y: prefersReduced ? 0 : 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: prefersReduced ? 0 : -8 }}
            transition={{
              duration: prefersReduced ? 0 : 0.45,
              ease: [0.4, 0, 0.2, 1],
            }}
          >
            {bt.layout.style === 'editorial' && <EditorialLayout {...layoutProps} />}
            {bt.layout.style === 'bold-grid' && <BoldGridLayout {...layoutProps} />}
            {bt.layout.style === 'minimal-dark' && <MinimalDarkLayout {...layoutProps} />}
            {bt.layout.style === 'warm-craft' && <WarmCraftLayout {...layoutProps} />}
          </motion.div>
        </AnimatePresence>
      </StoreShell>
    )
  }

  // ── Fallback path (no brand_token) ────────────────────────────────────────
  // Matches the original Storefront.tsx layout exactly so existing stores
  // look unchanged after this refactor.
  return (
    <main style={theme.cssVars}>
      {promoBar}
      {cartBtn}
      <Cart />

      <div className="max-w-5xl mx-auto px-5 py-12">
        <motion.header
          initial={{ opacity: 0, y: prefersReduced ? 0 : 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: prefersReduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
          className="flex flex-col items-center text-center gap-3 mb-12"
        >
          <BrandLogo
            logoUrl={store.logo_url}
            logoMark={store.icons.logo_mark}
            storeName={store.store_name}
            className="w-16 h-16"
          />
          <h1
            className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight break-words max-w-2xl [text-wrap:balance]"
            style={{ fontFamily: 'var(--s-display)' }}
          >
            {store.store_name}
          </h1>
          <p className="text-base" style={{ color: 'var(--s-accent-text)' }}>
            {store.tagline}
          </p>
        </motion.header>

        {store.products.length > 0 && (
          <div className="mb-8 flex flex-col gap-4">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
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

        <footer
          className="text-center mt-16 text-xs font-mono"
          style={{ color: 'var(--s-text-subtle)' }}
        >
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
