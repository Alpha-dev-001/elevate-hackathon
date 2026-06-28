'use client'
import { useEffect, useState } from 'react'
import type { SectionProps } from '@/lib/dslRegistry'

export function AnnouncementBarBanner({ store, slug, props }: SectionProps) {
  const c = store.brand_token!.colors
  const [dismissed, setDismissed] = useState(false)
  const key = `elevate-dismiss-${slug}`
  const code = (props?.code as string) || 'LAUNCH15'

  useEffect(() => {
    if (typeof window !== 'undefined' && localStorage.getItem(key) === '1') setDismissed(true)
  }, [key])

  if (dismissed) return null
  return (
    <div data-banner="announcement-bar"
         className="w-full h-11 flex items-center justify-center gap-3 px-4 text-xs md:text-sm relative"
         style={{ background: c.accent, color: c.background }}>
      <span>Use <strong>{code}</strong> for 15% off</span>
      <button aria-label="Dismiss" className="absolute right-3 text-base leading-none"
              onClick={() => { setDismissed(true); try { localStorage.setItem(key, '1') } catch {} }}>×</button>
    </div>
  )
}
