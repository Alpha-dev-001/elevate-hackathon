'use client'
import type { CardProps } from '@/lib/dslRegistry'
import { ProductImage } from '@/components/storefront/ProductImage'

export function EditorialHorizontalCard({ product, onOpen }: CardProps) {
  return (
    <button data-card="editorial-horizontal" data-product onClick={() => onOpen?.(product.id)}
            className="grid grid-cols-[45%_55%] sm:grid-cols-[45%_55%] w-full text-left items-stretch"
            style={{ borderBottom: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)' }}>
      <div className="aspect-[4/5] overflow-hidden" style={{ background: 'var(--s-surface)' }}>
        <ProductImage src={product.image_url} alt={product.name} initial={product.name} className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col justify-center gap-1 p-4">
        <span className="font-medium" style={{ fontFamily: 'var(--s-display)', color: 'var(--s-text)' }}>{product.name}</span>
        <span className="text-sm font-mono" style={{ color: 'var(--s-accent)' }}>${product.price}</span>
        {product.description && <span className="text-xs line-clamp-2" style={{ color: 'var(--s-text-muted)' }}>{product.description}</span>}
      </div>
    </button>
  )
}
