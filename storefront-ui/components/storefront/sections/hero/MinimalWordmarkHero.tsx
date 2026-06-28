'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function MinimalWordmarkHero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const c = store.brand_token!.colors
  return (
    <header data-hero
            className="flex flex-col justify-center min-h-[70vh] px-6 md:px-12"
            style={{ background: c.background, color: c.text }}>
      <motion.h1
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ duration: reduced ? 0 : 0.6, ease: [0.4, 0, 0.2, 1] }}
        className="font-black leading-[0.9] tracking-tight"
        style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(3.5rem, 18vw, 16rem)' }}>
        {store.store_name}
      </motion.h1>
      <p className="mt-4 text-[11px] font-mono uppercase tracking-[0.3em]"
         style={{ color: c.text_muted, opacity: 0.6 }}>
        {store.tagline}
      </p>
    </header>
  )
}
