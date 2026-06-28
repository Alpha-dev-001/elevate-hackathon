import type { ComponentType } from 'react'
import type { PublicStore, LayoutGlobalConfig } from '@/types/schemas'

export interface SectionProps {
  store: PublicStore
  slug: string
  variant: string
  globalConfig: LayoutGlobalConfig
  preview?: boolean
  onOpenProduct?: (id: string) => void
  onAddToCart?: (id: string) => void
  props?: Record<string, unknown>
}
export interface NavProps {
  store: PublicStore
  activeCategory: string | null
  onSelect: (c: string | null) => void
}
export interface CardProps {
  product: PublicStore['products'][number]
  slug: string
  cornerRadius: LayoutGlobalConfig['corner_radius']
  preview?: boolean
  onOpen?: (id: string) => void
  /** DSL-driven: where/whether the inline add-to-cart shows on the card. */
  addToCart?: LayoutGlobalConfig['add_to_cart']
  onAddToCart?: (id: string) => void
}

// Registries are filled by Tasks 10-14. Keys MUST match the Zod enums exactly.
export const SECTION_REGISTRY: Record<string, Record<string, ComponentType<SectionProps>>> = {
  hero: {},
  product_grid: {},
  banner: {},
  story: {},
}
export const CARD_REGISTRY: Record<string, ComponentType<CardProps>> = {}
export const NAV_REGISTRY: Record<string, ComponentType<NavProps>> = {}

/** Variant keys available per section type — used by the builder's variant pickers. */
export function variantsByType(type: string): string[] {
  return Object.keys(SECTION_REGISTRY[type] ?? {})
}

// ─── Point-and-edit: an addressable target in the rendered store ───────────────
export type EditTarget =
  | { kind: 'section'; index: number; sectionType: string; variant: string }
  | { kind: 'global'; field: 'nav_style' | 'product_card' | 'add_to_cart' | 'product_detail' | 'cart_style' }

/** Option values per editable global field (mirror schemas.ts enums exactly). */
export const GLOBAL_OPTIONS: Record<string, string[]> = {
  nav_style: ['underline-tabs', 'pill-nav', 'sidebar-text', 'sticky-tabs', 'minimal-text'],
  product_card: ['hover-reveal-text', 'colored-bg-card', 'editorial-horizontal', 'borderless-floating', 'polaroid-card', 'image-below-text'],
  add_to_cart: ['drawer-only', 'card-hover', 'card-always', 'none'],
  product_detail: ['gallery-split', 'editorial-stacked', 'minimal-centered'],
  cart_style: ['slide-panel', 'full-sheet'],
}
