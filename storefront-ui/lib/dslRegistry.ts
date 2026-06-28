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
