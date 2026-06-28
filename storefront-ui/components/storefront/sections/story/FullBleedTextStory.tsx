'use client'
import type { SectionProps } from '@/lib/dslRegistry'

export function FullBleedTextStory({ store }: SectionProps) {
  const c = store.brand_token!.colors
  return (
    <section data-story="full-bleed-text" className="px-6 py-24" style={{ background: c.surface, color: c.text }}>
      <div className="max-w-[680px] mx-auto text-center">
        <p className="text-2xl md:text-3xl font-light mb-6" style={{ fontFamily: 'var(--s-display)', color: c.accent }}>
          {store.tagline}
        </p>
        <p className="text-lg md:text-2xl leading-relaxed" style={{ fontFamily: 'var(--s-body)', color: c.text_muted }}>
          {store.brand_token!.brand_voice}
        </p>
      </div>
    </section>
  )
}
