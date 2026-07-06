'use client'
import { useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function ScrollTickerBanner({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const c = store.brand_token!.colors
  const text = store.tagline || 'NEW DROP'
  const items = Array.from({ length: 8 }, () => text)
  return (
    <div data-banner="scroll-ticker" className="overflow-hidden h-9 flex items-center group"
         style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
      <div className="flex whitespace-nowrap gap-6 px-3 text-xs uppercase tracking-widest"
           style={
             reduced
               ? undefined
               : { animation: 'elevate-ticker 30s linear infinite' }
           }>
        {items.map((t, i) => <span key={i} className="flex items-center gap-6">{t}<span aria-hidden>✦</span></span>)}
      </div>
      <style>{`@keyframes elevate-ticker{from{transform:translateX(0)}to{transform:translateX(-50%)}} [data-banner="scroll-ticker"]:hover div{animation-play-state:paused}`}</style>
    </div>
  )
}
