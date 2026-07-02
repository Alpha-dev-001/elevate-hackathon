'use client'
import type { SectionProps } from '@/lib/dslRegistry'
import { CARD_REGISTRY } from '@/lib/dslRegistry'
import { CardAddToCart } from '@/components/storefront/cards/CardAddToCart'
import { ProductImage } from '@/components/storefront/ProductImage'

export function HorizontalScrollGrid({ store, slug, globalConfig, onOpenProduct, onAddToCart, preview }: SectionProps) {
  const Card = CARD_REGISTRY[globalConfig.product_card]
  const radius = globalConfig.corner_radius
  const atc = globalConfig.add_to_cart
  return (
    <section data-grid="horizontal-scroll" className="py-12">
      <div className="flex gap-4 overflow-x-auto px-4 md:px-8 snap-x snap-mandatory">
        {store.products.map((p) => (
          <div key={p.id} className="snap-start shrink-0 w-[200px] md:w-[280px] relative group">
            <CardAddToCart product={p} addToCart={atc} onAddToCart={onAddToCart} preview={preview} />
            {Card ? (
              <Card product={p} slug={slug} cornerRadius={radius} onOpen={onOpenProduct} />
            ) : (
              <button data-product onClick={() => onOpenProduct?.(p.id)}
                      className="block w-full aspect-[3/4] text-left" style={{ background: 'var(--s-surface)' }}>
                <ProductImage src={p.image_url} alt={p.name} initial={p.name} className="w-full h-full object-cover" />
                <span className="block p-2 text-sm" style={{ color: 'var(--s-text)' }}>{p.name} · ${p.price}</span>
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="mx-4 md:mx-8 mt-4 h-0.5 rounded-full" style={{ background: 'var(--s-surface)' }} />
    </section>
  )
}
