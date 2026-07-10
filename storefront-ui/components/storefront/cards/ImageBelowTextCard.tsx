'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { RADIUS } from './radius'
import { ProductImage } from '@/components/storefront/ProductImage'
import { CardPrice } from './CardPrice'

export function ImageBelowTextCard({ product, cornerRadius, onOpen }: CardProps) {
  return (
    <button data-card="image-below-text" data-product data-product-id={product.id} onClick={() => onOpen?.(product.id)}
            className="block w-full text-left">
      {product.category && (
        <span className="block text-[10px] uppercase tracking-widest" style={{ color: 'var(--s-text-muted)' }}>
          {product.category}
        </span>
      )}
      <span className="block text-lg font-medium" style={{ fontFamily: 'var(--s-display)', color: 'var(--s-text)' }}>
        {product.name}
      </span>
      <span className="block text-xs mb-2" style={{ color: 'var(--s-cta)' }}><CardPrice product={product} /></span>
      <div className="w-full aspect-[3/4] overflow-hidden" style={{ borderRadius: RADIUS[cornerRadius], background: 'var(--s-surface)' }}>
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      </div>
    </button>
  )
}
