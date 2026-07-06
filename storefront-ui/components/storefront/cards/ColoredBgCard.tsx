'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { RADIUS } from './radius'
import { ProductImage } from '@/components/storefront/ProductImage'

export function ColoredBgCard({ product, cornerRadius, onOpen }: CardProps) {
  return (
    <button data-card="colored-bg-card" data-product onClick={() => onOpen?.(product.id)}
            className="block w-full text-left p-4"
            style={{ borderRadius: RADIUS[cornerRadius], background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
      <div className="w-full aspect-square flex items-center justify-center">
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-contain" />
      </div>
      <span className="block mt-3 font-medium">{product.name}</span>
      <span className="block text-sm opacity-80">${product.price}</span>
    </button>
  )
}
