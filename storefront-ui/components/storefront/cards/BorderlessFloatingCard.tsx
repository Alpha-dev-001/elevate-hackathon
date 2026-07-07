'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { ProductImage } from '@/components/storefront/ProductImage'
import { CardPrice } from './CardPrice'

export function BorderlessFloatingCard({ product, onOpen }: CardProps) {
  return (
    <button data-card="borderless-floating" data-product onClick={() => onOpen?.(product.id)}
            className="block w-full text-left group">
      <div className="w-full aspect-[3/4] overflow-hidden">
        <ProductImage src={product.image_url} alt={product.name} initial={product.name}
               className="w-full h-full object-cover transition-transform duration-[400ms] ease-out group-hover:scale-[1.03]" />
      </div>
      <span className="block mt-3 text-sm font-mono" style={{ color: 'var(--s-text)' }}>{product.name}</span>
      <span className="block text-sm font-mono" style={{ color: 'var(--s-text-muted)' }}><CardPrice product={product} /></span>
    </button>
  )
}
