'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { RADIUS } from './radius'

export function ColoredBgCard({ product, cornerRadius, onOpen }: CardProps) {
  return (
    <button data-card="colored-bg-card" data-product onClick={() => onOpen?.(product.id)}
            className="block w-full text-left p-4"
            style={{ borderRadius: RADIUS[cornerRadius], background: 'var(--s-accent)', color: 'var(--s-bg)' }}>
      <div className="w-full aspect-square flex items-center justify-center">
        {product.image_url && <img src={product.image_url} alt={product.name} className="max-w-full max-h-full object-contain" />}
      </div>
      <span className="block mt-3 font-medium">{product.name}</span>
      <span className="block text-sm opacity-80">${product.price}</span>
    </button>
  )
}
