'use client'
import type { SectionProps } from '@/lib/dslRegistry'

export function StaticStripBanner({ store }: SectionProps) {
  const c = store.brand_token!.colors
  return (
    <div data-banner="static-strip"
         className="w-full min-h-[80px] flex flex-wrap items-center justify-center gap-4 px-6 py-4 text-center"
         style={{ background: c.primary, color: c.background }}>
      <span className="text-sm md:text-base font-medium">{store.tagline}</span>
      <span className="inline-flex px-4 py-2 text-sm font-medium rounded-full"
            style={{ background: c.accent, color: c.background }}>Shop now</span>
    </div>
  )
}
