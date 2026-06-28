'use client'
import type { SectionProps } from '@/lib/dslRegistry'
import { CARD_REGISTRY } from '@/lib/dslRegistry'

export function HorizontalScrollGrid({ store, slug, globalConfig, onOpenProduct }: SectionProps) {
  const Card = CARD_REGISTRY[globalConfig.product_card]
  const radius = globalConfig.corner_radius
  return (
    <section data-grid="horizontal-scroll" className="py-12">
      <div className="flex gap-4 overflow-x-auto px-4 md:px-8 snap-x snap-mandatory">
        {store.products.map((p) => (
          <div key={p.id} className="snap-start shrink-0 w-[200px] md:w-[280px]">
            {Card ? (
              <Card product={p} slug={slug} cornerRadius={radius} onOpen={onOpenProduct} />
            ) : (
              <button data-product onClick={() => onOpenProduct?.(p.id)}
                      className="block w-full aspect-[3/4] text-left" style={{ background: 'var(--s-surface)' }}>
                {p.image_url && <img src={p.image_url} alt={p.name} className="w-full h-full object-cover" />}
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
