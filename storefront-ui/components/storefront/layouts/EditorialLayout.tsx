'use client'

import type { PublicProduct, PublicStore } from '@/types/schemas'
import { HeroSection } from '@/components/store/HeroSection'
import { CategoryNav } from '@/components/store/CategoryNav'
import { ProductGrid } from '@/components/storefront/ProductGrid'

/**
 * Editorial — clean, magazine-style layout.
 *
 * Structure:
 *   Full-width typographic hero (usually text-forward or full-bleed hero type)
 *   ─────── thin rule ───────
 *   Underline-tab category nav
 *   Search bar
 *   2col-featured product grid (first item gets the hero treatment)
 *
 * Visual identity: generous whitespace, large display type, narrow readable
 * column, soft gradient header, editorial spacing throughout.
 */

interface EditorialLayoutProps {
  store: PublicStore
  slug: string
  filtered: PublicProduct[]
  query: string
  setQuery: React.Dispatch<React.SetStateAction<string>>
  activeCategory: string | null
  setActiveCategory: React.Dispatch<React.SetStateAction<string | null>>
}

export function EditorialLayout({
  store,
  slug,
  filtered,
  query,
  setQuery,
  activeCategory,
  setActiveCategory,
}: EditorialLayoutProps) {
  const bt = store.brand_token!

  return (
    <div>
      {/* Hero */}
      <HeroSection
        brandToken={bt}
        storeName={store.store_name}
        tagline={store.tagline}
        logoMark={store.icons.logo_mark}
      />

      {/* Thin rule separator */}
      <div
        className="mx-auto max-w-5xl px-6"
        style={{ borderTop: `1px solid color-mix(in srgb, var(--s-text) 10%, transparent)` }}
      />

      <div className="max-w-5xl mx-auto px-6 py-12">
        {/* Category nav — underline-tab for editorial feel */}
        {store.categories.length > 0 && (
          <CategoryNav
            categories={store.categories}
            active={activeCategory}
            onSelect={setActiveCategory}
            brandToken={bt}
          />
        )}

        {/* Search */}
        {store.products.length > 0 && (
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products…"
            className="w-full rounded-lg px-4 py-2.5 text-sm outline-none mb-10"
            style={{
              background: 'color-mix(in srgb, var(--s-text) 5%, var(--s-bg))',
              color: 'var(--s-text)',
              border: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)',
            }}
          />
        )}

        {/* Products — 2col-featured grid with editorial card style */}
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
          className="text-center mt-20 text-xs font-mono"
          style={{ color: 'var(--s-text-subtle)' }}
        >
          Powered by Elevate
        </footer>
      </div>
    </div>
  )
}
