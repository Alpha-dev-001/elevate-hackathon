'use client'
import type { CardProps } from '@/lib/dslRegistry'

/**
 * Inline add-to-cart affordance for product cards. Visibility is DSL-driven
 * ("shared autonomy" — flexibility, not a hardcoded fix):
 *   - 'card-always'  → always visible
 *   - 'card-hover'   → revealed on group-hover (desktop) / always (touch)
 *   - 'drawer-only' | 'none' | undefined → card renders nothing here
 * The parent card must be a `.group` for hover mode to work.
 */
export function CardAddToCart({
  product, addToCart, onAddToCart, preview,
}: Pick<CardProps, 'product' | 'addToCart' | 'onAddToCart' | 'preview'>) {
  if (addToCart !== 'card-always' && addToCart !== 'card-hover') return null

  const hoverReveal = addToCart === 'card-hover'
  return (
    <button
      type="button"
      disabled={preview || !product.available}
      onClick={(e) => {
        e.stopPropagation()      // don't open the drawer
        if (!preview) onAddToCart?.(product.id)
      }}
      aria-label={`Add ${product.name} to cart`}
      className={[
        'absolute bottom-2 right-2 z-20 px-3 py-1.5 rounded-full text-xs font-medium',
        'transition-all duration-200 disabled:opacity-50',
        hoverReveal
          ? 'opacity-0 translate-y-1 group-hover:opacity-100 group-hover:translate-y-0 [@media(hover:none)]:opacity-100 [@media(hover:none)]:translate-y-0'
          : 'opacity-100',
      ].join(' ')}
      style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
    >
      {product.available ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
          <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
        </svg>
      ) : 'Sold out'}
    </button>
  )
}
