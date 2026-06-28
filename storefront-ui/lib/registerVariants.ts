/**
 * Central variant registration. Importing this module (side-effect) populates
 * the SECTION/CARD/NAV registries. DSLRenderer and tests import it once so the
 * registries are filled before any lookup. Each family task appends here.
 */
import { SECTION_REGISTRY } from '@/lib/dslRegistry'

// ─── Hero family (Task 10) ──────────────────────────────────────────────────
import { EditorialStackedHero } from '@/components/storefront/sections/hero/EditorialStackedHero'
import { FullBleedImageHero } from '@/components/storefront/sections/hero/FullBleedImageHero'
import { MinimalWordmarkHero } from '@/components/storefront/sections/hero/MinimalWordmarkHero'
import { Split5050Hero } from '@/components/storefront/sections/hero/Split5050Hero'

SECTION_REGISTRY.hero['editorial-stacked'] = EditorialStackedHero
SECTION_REGISTRY.hero['full-bleed-image'] = FullBleedImageHero
SECTION_REGISTRY.hero['minimal-wordmark'] = MinimalWordmarkHero
SECTION_REGISTRY.hero['split-50-50'] = Split5050Hero

// ─── Product-grid family (Task 11) ──────────────────────────────────────────
import { Featured2ColGrid } from '@/components/storefront/sections/product-grid/Featured2ColGrid'
import { Masonry4ColGrid } from '@/components/storefront/sections/product-grid/Masonry4ColGrid'
import { HorizontalScrollGrid } from '@/components/storefront/sections/product-grid/HorizontalScrollGrid'
import { SingleSpotlightGrid } from '@/components/storefront/sections/product-grid/SingleSpotlightGrid'

SECTION_REGISTRY.product_grid['featured-2col'] = Featured2ColGrid
SECTION_REGISTRY.product_grid['masonry-4col'] = Masonry4ColGrid
SECTION_REGISTRY.product_grid['horizontal-scroll'] = HorizontalScrollGrid
SECTION_REGISTRY.product_grid['single-spotlight'] = SingleSpotlightGrid
