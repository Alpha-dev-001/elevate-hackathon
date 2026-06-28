'use client'
import type { SectionProps } from '@/lib/dslRegistry'

export function QuoteCalloutStory({ store }: SectionProps) {
  const c = store.brand_token!.colors
  return (
    <section data-story="quote-callout" className="px-6 py-24 text-center" style={{ background: c.surface, color: c.text }}>
      <span aria-hidden className="block leading-none mb-2" style={{ fontSize: 120, color: c.accent, fontFamily: 'var(--s-display)' }}>“</span>
      <blockquote className="max-w-3xl mx-auto text-2xl md:text-4xl font-light" style={{ fontFamily: 'var(--s-display)' }}>
        {store.tagline}
      </blockquote>
      <p className="mt-6 text-sm" style={{ color: c.text_muted }}>— {store.store_name} founder</p>
    </section>
  )
}
