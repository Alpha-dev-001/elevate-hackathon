/**
 * Central variant registration. Importing this module (side-effect) populates
 * the SECTION/CARD/NAV registries. DSLRenderer and tests import it once so the
 * registries are filled before any lookup. Each family task appends here.
 */
import { SECTION_REGISTRY, CARD_REGISTRY } from '@/lib/dslRegistry'

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

// ─── Product-card family (Task 12) ──────────────────────────────────────────
import { HoverRevealCard } from '@/components/storefront/cards/HoverRevealCard'
import { ColoredBgCard } from '@/components/storefront/cards/ColoredBgCard'
import { EditorialHorizontalCard } from '@/components/storefront/cards/EditorialHorizontalCard'
import { BorderlessFloatingCard } from '@/components/storefront/cards/BorderlessFloatingCard'
import { PolaroidCard } from '@/components/storefront/cards/PolaroidCard'
import { ImageBelowTextCard } from '@/components/storefront/cards/ImageBelowTextCard'

CARD_REGISTRY['hover-reveal-text'] = HoverRevealCard
CARD_REGISTRY['colored-bg-card'] = ColoredBgCard
CARD_REGISTRY['editorial-horizontal'] = EditorialHorizontalCard
CARD_REGISTRY['borderless-floating'] = BorderlessFloatingCard
CARD_REGISTRY['polaroid-card'] = PolaroidCard
CARD_REGISTRY['image-below-text'] = ImageBelowTextCard

// ─── Banner family (Task 13) ────────────────────────────────────────────────
import { ScrollTickerBanner } from '@/components/storefront/sections/banner/ScrollTickerBanner'
import { StaticStripBanner } from '@/components/storefront/sections/banner/StaticStripBanner'
import { AnnouncementBarBanner } from '@/components/storefront/sections/banner/AnnouncementBarBanner'

SECTION_REGISTRY.banner['scroll-ticker'] = ScrollTickerBanner
SECTION_REGISTRY.banner['static-strip'] = StaticStripBanner
SECTION_REGISTRY.banner['announcement-bar'] = AnnouncementBarBanner

// ─── Story family (Task 13) ─────────────────────────────────────────────────
import { FullBleedTextStory } from '@/components/storefront/sections/story/FullBleedTextStory'
import { SplitImageStory } from '@/components/storefront/sections/story/SplitImageStory'
import { QuoteCalloutStory } from '@/components/storefront/sections/story/QuoteCalloutStory'

SECTION_REGISTRY.story['full-bleed-text'] = FullBleedTextStory
SECTION_REGISTRY.story['split-image-story'] = SplitImageStory
SECTION_REGISTRY.story['quote-callout'] = QuoteCalloutStory
