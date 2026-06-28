'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function FullBleedImageHero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const c = store.brand_token!.colors
  const featured = store.products.find((p) => p.image_url) ?? store.products[0]
  return (
    <header
      data-hero
      className="relative w-full h-[58vh] md:h-[78vh] overflow-hidden flex items-end"
      style={{ background: c.background }}
    >
      {featured?.image_url && (
        <img
          src={featured.image_url}
          alt=""
          aria-hidden
          className="absolute inset-0 w-full h-full object-cover"
        />
      )}
      {/* Bottom-anchored scrim so the wordmark always reads, never clipped. */}
      <div
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-1/2"
        style={{ background: 'linear-gradient(transparent, rgba(0,0,0,0.78))' }}
      />
      <span
        className="absolute top-4 right-4 z-10 text-xs font-mono px-2.5 py-1 rounded-full"
        style={{ background: c.accent, color: c.background }}
      >
        {store.products.length} pieces
      </span>
      <motion.h1
        initial={{ opacity: 0, y: reduced ? 0 : 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="relative z-10 px-6 md:px-12 pb-8 md:pb-12 font-black text-white leading-[0.95] [text-wrap:balance]"
        style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(2.5rem, 8vw, 6rem)' }}
      >
        {store.store_name}
      </motion.h1>
    </header>
  )
}
