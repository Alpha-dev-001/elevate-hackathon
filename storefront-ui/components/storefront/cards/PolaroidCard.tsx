'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { ProductImage } from '@/components/storefront/ProductImage'

export function PolaroidCard({ product, onOpen }: CardProps) {
  return (
    <button data-card="polaroid-card" data-product onClick={() => onOpen?.(product.id)}
            className="block w-full text-left bg-white pb-10 pt-2 px-2 shadow-md">
      <div className="w-full aspect-[4/3] overflow-hidden">
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      </div>
      <span className="block mt-2 text-center text-sm italic text-neutral-600" style={{ fontFamily: 'var(--s-body)' }}>
        {product.name} · ${product.price}
      </span>
    </button>
  )
}
