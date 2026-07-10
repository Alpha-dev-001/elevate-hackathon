'use client'
import { useState } from 'react'
import type { CardProps } from '@/lib/dslRegistry'
import { RADIUS } from './radius'
import { ProductImage } from '@/components/storefront/ProductImage'
import { CardPrice } from './CardPrice'

export function HoverRevealCard({ product, cornerRadius, onOpen }: CardProps) {
  const [hover, setHover] = useState(false)
  return (
    <button data-card="hover-reveal-text" data-product data-product-id={product.id} onClick={() => onOpen?.(product.id)}
            onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
            className="relative block w-full aspect-[3/4] overflow-hidden text-left"
            style={{ borderRadius: RADIUS[cornerRadius], background: 'var(--s-surface)' }}>
      <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      <div className="absolute inset-0 flex flex-col justify-end p-3 transition-opacity duration-300"
           style={{ background: 'linear-gradient(transparent, rgba(0,0,0,0.6))', opacity: hover ? 1 : 0, color: '#fff' }}>
        <span className="font-medium">{product.name}</span>
        <span className="text-sm"><CardPrice product={product} /></span>
      </div>
    </button>
  )
}
