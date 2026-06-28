'use client'
import type { SectionProps } from '@/lib/dslRegistry'
import { CARD_REGISTRY } from '@/lib/dslRegistry'
import { CardAddToCart } from '@/components/storefront/cards/CardAddToCart'

export function Masonry4ColGrid({ store, slug, globalConfig, onOpenProduct, onAddToCart, preview }: SectionProps) {
  const Card = CARD_REGISTRY[globalConfig.product_card]
  const radius = globalConfig.corner_radius
  const atc = globalConfig.add_to_cart
  return (
    <section data-grid="masonry-4col"
             className="px-4 md:px-8 py-12 [column-fill:_balance] columns-2 md:columns-4 gap-3">
      {store.products.map((p) => (
        <div key={p.id} className="mb-3 break-inside-avoid relative group">
          <CardAddToCart product={p} addToCart={atc} onAddToCart={onAddToCart} preview={preview} />
          {Card ? (
            <Card product={p} slug={slug} cornerRadius={radius} onOpen={onOpenProduct} />
          ) : (
            <button data-product onClick={() => onOpenProduct?.(p.id)} className="block w-full text-left"
                    style={{ background: 'var(--s-surface)' }}>
              {p.image_url && <img src={p.image_url} alt={p.name} className="w-full object-cover" />}
              <span className="block p-2 text-sm" style={{ color: 'var(--s-text)' }}>{p.name} · ${p.price}</span>
            </button>
          )}
        </div>
      ))}
    </section>
  )
}
