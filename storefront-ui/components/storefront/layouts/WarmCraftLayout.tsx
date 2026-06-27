'use client'

import type { PublicProduct, PublicStore } from '@/types/schemas'
import { CategoryNav } from '@/components/store/CategoryNav'
import { ProductGrid } from '@/components/storefront/ProductGrid'

/**
 * Warm Craft — artisan, handmade, warm-and-inviting layout.
 *
 * Structure:
 *   Full-width radial gradient header (texture-bg feel) with large logo mark
 *   Store name in the brand's display font, centered
 *   Pill category nav below the fold
 *   Search bar
 *   Masonry or 2col-featured grid with elevated, generously-rounded cards
 *
 * Visual identity: warm tones from the brand palette, large rounded corners,
 * generous padding, logo mark as a design element, handcrafted feel.
 */

interface WarmCraftLayoutProps {
  store: PublicStore
  slug: string
  filtered: PublicProduct[]
  query: string
  setQuery: React.Dispatch<React.SetStateAction<string>>
  activeCategory: string | null
  setActiveCategory: React.Dispatch<React.SetStateAction<string | null>>
}

export function WarmCraftLayout({
  store,
  slug,
  filtered,
  query,
  setQuery,
  activeCategory,
  setActiveCategory,
}: WarmCraftLayoutProps) {
  const bt = store.brand_token!

  return (
    <div>
      {/* Texture-bg hero — radial gradient with centered logo and name */}
      <header
        className="relative w-full text-center py-20 md:py-28 px-6 overflow-hidden"
        style={{
          background: `radial-gradient(ellipse 90% 70% at 50% 0%, ${bt.colors.primary}50 0%, ${bt.colors.background} 72%)`,
        }}
      >
        {/* Decorative concentric rings — artisan texture cue */}
        <div
          className="absolute inset-0 pointer-events-none"
          aria-hidden="true"
          style={{
            backgroundImage: `radial-gradient(circle at 50% 0%, ${bt.colors.primary}18 0%, transparent 50%),
                              radial-gradient(circle at 50% 0%, ${bt.colors.primary}0C 0%, transparent 70%)`,
          }}
        />

        <div className="relative z-10">
          {store.icons.logo_mark && (
            <div
              className="w-24 h-24 mx-auto mb-6 [&>svg]:w-full [&>svg]:h-full"
              role="img"
              aria-label={`${store.store_name} logo`}
              dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }}
            />
          )}
          <h1
            className="text-4xl md:text-6xl font-bold mb-3 [text-wrap:balance] max-w-xl mx-auto"
            style={{
              fontFamily: 'var(--s-display)',
              letterSpacing: 'var(--s-letter-spacing)',
            }}
          >
            {store.store_name}
          </h1>
          <p
            className="text-base max-w-xs mx-auto"
            style={{ color: bt.colors.accent }}
          >
            {store.tagline}
          </p>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-5 py-10">
        {/* Pill category nav */}
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
            className="w-full px-4 py-3 text-sm outline-none mb-8"
            style={{
              background: `${bt.colors.primary}0A`,
              color: bt.colors.text,
              border: `1px solid ${bt.colors.primary}30`,
              borderRadius: bt.layout.border_radius,
            }}
          />
        )}

        {/* Product grid — elevated cards with generous border-radius */}
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
          className="text-center mt-16 text-xs"
          style={{ color: 'var(--s-text-subtle)', fontFamily: 'var(--s-display)' }}
        >
          Made with care · Powered by Elevate
        </footer>
      </div>
    </div>
  )
}
