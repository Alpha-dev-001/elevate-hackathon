import type { PublicProduct } from '@/types/schemas'

/**
 * Case/whitespace-insensitive substring match against name, description, and
 * category — same normalization philosophy as category.ts's sameCategory.
 * An empty query matches everything (no-op filter).
 */
export function matchesSearch(product: PublicProduct, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (q === '') return true
  return (
    product.name.toLowerCase().includes(q) ||
    (product.description ?? '').toLowerCase().includes(q) ||
    (product.category ?? '').toLowerCase().includes(q)
  )
}
