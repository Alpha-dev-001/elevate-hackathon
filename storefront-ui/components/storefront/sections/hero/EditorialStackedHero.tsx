'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function EditorialStackedHero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const featured = store.products[0]
  const c = store.brand_token!.colors
  const [l1, ...rest] = store.store_name.split(' ')
  return (
    <header data-hero className="relative overflow-hidden px-6 md:px-10 py-20 md:py-28"
            style={{ background: c.background, color: c.text }}>
      {featured?.image_url && (
        <div aria-hidden
             className="hidden md:block absolute top-0 right-0 h-full w-1/2 bg-cover bg-center opacity-90"
             style={{ backgroundImage: `url(${featured.image_url})` }} />
      )}
      <motion.h1
        initial={{ opacity: 0, y: reduced ? 0 : 24 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="relative z-10 font-black leading-[0.92] max-w-[60%]"
        style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(2.5rem, 11vw, 9rem)' }}>
        <span className="block">{l1}</span>
        {rest.length > 0 && <span className="block">{rest.join(' ')}</span>}
      </motion.h1>
      <p className="relative z-10 mt-6 text-xs md:text-sm uppercase tracking-[0.3em]"
         style={{ fontFamily: 'var(--s-body)', color: c.text_muted }}>
        {store.tagline}
      </p>
    </header>
  )
}
