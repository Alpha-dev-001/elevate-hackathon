'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function Split5050Hero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const c = store.brand_token!.colors
  const featured = store.products[0]
  return (
    <header data-hero className="grid md:grid-cols-2 min-h-[70vh]" style={{ background: c.background }}>
      <motion.div
        initial={{ opacity: 0, x: reduced ? 0 : -16 }} animate={{ opacity: 1, x: 0 }}
        transition={{ duration: reduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="flex flex-col justify-center gap-5 px-6 md:px-12 py-16 order-2 md:order-1"
        style={{ color: c.text }}>
        <h1 className="font-bold leading-tight"
            style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(2.25rem, 6vw, 4.5rem)' }}>
          {store.store_name}
        </h1>
        <p style={{ color: c.text_muted, fontFamily: 'var(--s-body)' }}>{store.tagline}</p>
        <span className="inline-flex w-fit px-5 py-2.5 text-sm font-medium rounded-full"
              style={{ background: c.accent, color: c.background }}>Shop the collection</span>
      </motion.div>
      <div className="order-1 md:order-2 h-[40vh] md:h-auto bg-cover bg-center"
           style={{
             background: featured?.image_url
               ? `url(${featured.image_url}) center/cover`
               : c.surface,
           }}
           aria-hidden />
    </header>
  )
}
