'use client'

import type { PublicProduct, PublicStore } from '@/types/schemas'
import { CategoryNav } from '@/components/store/CategoryNav'
import { ProductGrid } from '@/components/storefront/ProductGrid'
import { BrandLogo } from '@/components/storefront/BrandLogo'

/**
 * Bold Grid — high-energy, grid-first layout. No hero section.
 *
 * Structure:
 *   4px accent bar at the very top (brand's energy, instantly visible)
 *   Compact header row: store name (all-caps, heavy) + pill category nav
 *   Search bar
 *   Dense 3-column product grid with colored-bg cards
 *
 * Visual identity: high contrast, tight spacing, uppercase typography,
 * accent color used aggressively. The grid IS the hero.
 */

interface BoldGridLayoutProps {
  store: PublicStore
  slug: string
  filtered: PublicProduct[]
  query: string
  setQuery: React.Dispatch<React.SetStateAction<string>>
  activeCategory: string | null
  setActiveCategory: React.Dispatch<React.SetStateAction<string | null>>
}

export function BoldGridLayout({
  store,
  slug,
  filtered,
  query,
  setQuery,
  activeCategory,
  setActiveCategory,
}: BoldGridLayoutProps) {
  const bt = store.brand_token!

  return (
    <div>
      {/* Thick accent bar — brand energy, full width */}
      <div className="w-full h-1.5" style={{ background: bt.colors.accent }} />

      {/* Compact header */}
      <div
        className="px-5 py-5"
        style={{ background: bt.colors.surface }}
      >
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <BrandLogo
              decorative
              logoUrl={store.logo_url}
              logoMark={store.icons.logo_mark}
              storeName={store.store_name}
              className="w-8 h-8 shrink-0"
            />
            <h1
              className="text-xl font-black uppercase tracking-tighter leading-none"
              style={{
                fontFamily: 'var(--s-display)',
                color: bt.colors.text,
              }}
            >
              {store.store_name}
            </h1>
          </div>

          {/* Pill nav inline with header on larger screens */}
          {store.categories.length > 0 && (
            <div className="sm:ml-auto">
              <CategoryNav
                categories={store.categories}
                active={activeCategory}
                onSelect={setActiveCategory}
                brandToken={bt}
              />
            </div>
          )}
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-5 py-8">
        {/* Tagline */}
        <p
          className="text-xs font-mono uppercase tracking-[0.2em] mb-5"
          style={{ color: bt.colors.text_muted }}
        >
          {store.tagline}
        </p>

        {/* Search */}
        {store.products.length > 0 && (
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products…"
            className="w-full px-4 py-2.5 text-sm outline-none mb-6"
            style={{
              background: `${bt.colors.text}08`,
              color: bt.colors.text,
              border: `1.5px solid ${bt.colors.text}22`,
              borderRadius: bt.layout.border_radius,
            }}
          />
        )}

        {/* Dense product grid */}
        <ProductGrid
          products={filtered}
          logoMark={store.icons.logo_mark}
          slug={slug}
          emptyLabel={store.products.length === 0 ? 'Preparing the shelves' : 'Nothing matches'}
          emptySub={
            store.products.length === 0
              ? 'New pieces are on their way.'
              : 'Try a different search or category.'
          }
          gridVariant={bt.layout.product_grid}
          cardStyle={bt.layout.card_style}
          brandToken={bt}
        />

        <footer
          className="text-center mt-16 text-xs font-mono"
          style={{ color: 'var(--s-text-subtle)' }}
        >
          Powered by Elevate
        </footer>
      </div>
    </div>
  )
}
