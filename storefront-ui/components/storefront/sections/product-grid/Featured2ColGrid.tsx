'use client'
import type { SectionProps } from '@/lib/dslRegistry'
import { CARD_REGISTRY } from '@/lib/dslRegistry'
import { CardAddToCart } from '@/components/storefront/cards/CardAddToCart'
import { ProductImage } from '@/components/storefront/ProductImage'

export function Featured2ColGrid({ store, slug, globalConfig, onOpenProduct, onAddToCart, preview }: SectionProps) {
  const Card = CARD_REGISTRY[globalConfig.product_card]
  const [first, ...rest] = store.products
  const radius = globalConfig.corner_radius
  const atc = globalConfig.add_to_cart
  return (
    <section data-grid="featured-2col" className="px-4 md:px-8 py-12 grid gap-4 md:grid-cols-2">
      {first && (
        <button data-product onClick={() => onOpenProduct?.(first.id)}
                className="relative block w-full aspect-[3/4] overflow-hidden text-left"
                style={{ background: 'var(--s-surface)' }}>
          <ProductImage src={first.image_url} alt={first.name} initial={first.name} className="w-full h-full object-cover" />
          <span className="absolute bottom-3 left-3 font-medium" style={{ color: 'var(--s-text)' }}>
            {first.name} · ${first.price}
          </span>
        </button>
      )}
      <div className="grid grid-cols-2 gap-4">
        {rest.map((p) => (
          <div key={p.id} className="relative group">
            <CardAddToCart product={p} addToCart={atc} onAddToCart={onAddToCart} preview={preview} />
            {Card ? (
              <Card product={p} slug={slug} cornerRadius={radius} onOpen={onOpenProduct} />
            ) : (
              <button data-product onClick={() => onOpenProduct?.(p.id)} className="block text-left">
                {p.name} · ${p.price}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
