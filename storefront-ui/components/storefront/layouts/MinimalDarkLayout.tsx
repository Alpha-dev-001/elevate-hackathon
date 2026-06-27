'use client'

import type { PublicProduct, PublicStore } from '@/types/schemas'
import { CategoryNav } from '@/components/store/CategoryNav'
import { ProductGrid } from '@/components/storefront/ProductGrid'

/**
 * Minimal Dark — quiet, refined, whitespace-forward layout.
 *
 * Structure:
 *   Tiny header: store name in small-caps mono, minimal chrome
 *   Huge breathing room
 *   Minimal-text category links (plain uppercase text, no chrome)
 *   Search bar (barely visible)
 *   Masonry product grid with borderless cards
 *   Footer
 *
 * Visual identity: less is more. Dark surface, muted colors, thin type,
 * generous whitespace. Feels like a luxury brand microsite.
 */

interface MinimalDarkLayoutProps {
  store: PublicStore
  slug: string
  filtered: PublicProduct[]
  query: string
  setQuery: React.Dispatch<React.SetStateAction<string>>
  activeCategory: string | null
  setActiveCategory: React.Dispatch<React.SetStateAction<string | null>>
}

export function MinimalDarkLayout({
  store,
  slug,
  filtered,
  query,
  setQuery,
  activeCategory,
  setActiveCategory,
}: MinimalDarkLayoutProps) {
  const bt = store.brand_token!

  return (
    <div className="min-h-screen">
      {/* Minimal top bar */}
      <header
        className="w-full px-8 py-5 flex items-center justify-between"
        style={{ borderBottom: `1px solid ${bt.colors.text}10` }}
      >
        <div className="flex items-center gap-3">
          {store.icons.logo_mark && (
            <div
              className="w-5 h-5 [&>svg]:w-full [&>svg]:h-full opacity-60"
              aria-hidden="true"
              dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }}
            />
          )}
          <span
            className="text-[11px] font-mono uppercase tracking-[0.3em]"
            style={{ color: bt.colors.text_muted }}
          >
            {store.store_name}
          </span>
        </div>
        <span
          className="text-[10px] font-mono uppercase tracking-[0.15em]"
          style={{ color: bt.colors.text_muted }}
        >
          {store.tagline}
        </span>
      </header>

      {/* Generous breathing room */}
      <div className="h-16 md:h-24" />

      <main className="max-w-4xl mx-auto px-8">
        {/* Minimal-text category nav */}
        {store.categories.length > 0 && (
          <CategoryNav
            categories={store.categories}
            active={activeCategory}
            onSelect={setActiveCategory}
            brandToken={bt}
          />
        )}

        {/* Ghost search — barely-there styling */}
        {store.products.length > 0 && (
          <div
            className="flex items-center gap-3 mb-12 pb-3"
            style={{ borderBottom: `1px solid ${bt.colors.text}0C` }}
          >
            <span
              className="text-[10px] font-mono uppercase tracking-[0.2em]"
              style={{ color: bt.colors.text_muted }}
            >
              Search
            </span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="…"
              className="flex-1 bg-transparent text-sm outline-none"
              style={{ color: bt.colors.text }}
            />
          </div>
        )}

        {/* Masonry grid — borderless cards, lots of whitespace between */}
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

        <div className="h-20" />
      </main>

      <footer
        className="text-center py-8 text-[10px] font-mono tracking-widest uppercase"
        style={{ color: `${bt.colors.text_muted}66` }}
      >
        Powered by Elevate
      </footer>
    </div>
  )
}
