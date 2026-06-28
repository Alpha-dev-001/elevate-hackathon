'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function FullBleedImageHero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const c = store.brand_token!.colors
  const featured = store.products[0]
  return (
    <header data-hero
            className="relative w-full h-[60vh] md:h-screen overflow-hidden flex items-end"
            style={{ background: c.background }}>
      {featured?.image_url && (
        <img src={featured.image_url} alt="" aria-hidden
             className="absolute inset-0 w-full h-full object-cover" />
      )}
      <div aria-hidden className="absolute inset-0"
           style={{ background: 'linear-gradient(transparent 35%, rgba(0,0,0,0.72))' }} />
      <span className="absolute top-4 right-4 z-10 text-xs font-mono px-2 py-1 rounded-full"
            style={{ background: c.accent, color: c.background }}>
        {store.products.length} pieces
      </span>
      <motion.h1
        initial={{ opacity: 0, y: reduced ? 0 : 20 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="relative z-10 px-6 md:px-12 pb-10 font-black text-white leading-[0.95]"
        style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(2.5rem, 9vw, 7rem)' }}>
        {store.store_name}
      </motion.h1>
      <nav className="absolute bottom-0 left-0 right-0 z-10 flex gap-4 overflow-x-auto px-6 md:px-12 py-3 text-xs uppercase tracking-wide text-white/80">
        {store.categories.map((cat) => <span key={cat} className="whitespace-nowrap">{cat}</span>)}
      </nav>
    </header>
  )
}
