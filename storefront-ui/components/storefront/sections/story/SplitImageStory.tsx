'use client'
import type { SectionProps } from '@/lib/dslRegistry'

export function SplitImageStory({ store, props }: SectionProps) {
  const c = store.brand_token!.colors
  const featured = store.products[0]
  const imageRight = props?.image_side === 'right'
  const img = (
    <div className="h-[200px] md:h-auto bg-cover bg-center" aria-hidden
         style={{ background: featured?.image_url ? `url(${featured.image_url}) center/cover` : c.surface }} />
  )
  const text = (
    <div className="flex flex-col justify-center gap-4 px-6 md:px-12 py-12" style={{ color: c.text }}>
      <p className="text-lg md:text-xl leading-relaxed" style={{ fontFamily: 'var(--s-body)' }}>
        {store.brand_token!.brand_voice}
      </p>
      <span className="text-sm" style={{ color: c.text_muted }}>— {store.store_name}</span>
    </div>
  )
  return (
    <section data-story="split-image-story" className="grid md:grid-cols-[40%_60%]" style={{ background: c.background }}>
      {imageRight ? <>{text}{img}</> : <>{img}{text}</>}
    </section>
  )
}
