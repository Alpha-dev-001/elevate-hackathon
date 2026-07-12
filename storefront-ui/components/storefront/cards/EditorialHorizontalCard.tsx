'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { ProductImage } from '@/components/storefront/ProductImage'
import { CardPrice } from './CardPrice'

/**
 * Editorial in typography/spacing, not in a side-by-side image+text split —
 * every grid variant that hosts cards (masonry-4col, featured-2col's rest
 * grid, horizontal-scroll) only gives a card 200-300px of width, nowhere
 * near enough room for a 45/55 horizontal split to read cleanly. Stacks
 * vertically like the other 5 card variants; stays visually distinct via
 * the display-font name, the rule under the image, and the description
 * (the only other card variant that shows one is image-below-text).
 */
export function EditorialHorizontalCard({ product, onOpen }: CardProps) {
  return (
    <button data-card="editorial-horizontal" data-product data-product-id={product.id} onClick={() => onOpen?.(product.id)}
            className="block w-full text-left">
      <div className="aspect-[4/5] overflow-hidden" style={{ background: 'var(--s-surface)' }}>
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col gap-1 pt-3 mt-3"
           style={{ borderTop: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)' }}>
        <span className="font-medium leading-snug" style={{ fontFamily: 'var(--s-display)', color: 'var(--s-text)' }}>{product.name}</span>
        <span className="text-sm font-mono" style={{ color: 'var(--s-cta)' }}><CardPrice product={product} /></span>
        {product.description && <span className="text-xs line-clamp-2" style={{ color: 'var(--s-text-muted)' }}>{product.description}</span>}
      </div>
    </button>
  )
}
