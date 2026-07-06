'use client'
import { useState } from 'react'
import type { PublicStore } from '@/types/schemas'
import { NAV_REGISTRY } from '@/lib/dslRegistry'
import { BrandLogo } from '@/components/storefront/BrandLogo'

export function DSLNav({ store, navStyle, preview }: { store: PublicStore; navStyle: string; preview?: boolean }) {
  const [active, setActive] = useState<string | null>(null)
  const Comp = NAV_REGISTRY[navStyle]

  // Persistent brand lockup — the merchant's real uploaded logo (falls back to
  // Qwen's SVG mark), top-left, where shoppers look for it. This is the store's
  // identity on every page; the category nav renders beneath it.
  //
  // A real uploaded logo usually already contains the store name, so we show it
  // prominently and DON'T repeat the name as text. The generated SVG mark is a
  // wordless glyph, so when we fall back to it we pair it with the store name.
  const hasRealLogo = !!store.logo_url && store.logo_url.trim() !== ''
  const brand = (
    <div className="flex items-center gap-2.5 px-5 md:px-10 pt-5 pb-2">
      <BrandLogo
        logoUrl={store.logo_url}
        logoMark={store.icons.logo_mark}
        storeName={store.store_name}
        className={hasRealLogo ? 'h-12 w-auto max-w-[240px] min-w-[3rem]' : 'h-9 w-9'}
      />
      {!hasRealLogo && (
        <span
          className="text-base font-semibold tracking-tight"
          style={{ fontFamily: 'var(--s-display)', color: 'var(--s-text)' }}
        >
          {store.store_name}
        </span>
      )}
    </div>
  )

  if (Comp) {
    return (
      <div data-nav={navStyle}>
        {brand}
        <Comp store={store} activeCategory={active} onSelect={setActive} preview={preview} />
      </div>
    )
  }
  // Minimal inline fallback until the nav family lands (Task 14).
  return (
    <div data-nav={navStyle}>
      {brand}
      <nav className="flex gap-3 px-5 py-3 text-sm">
        <button onClick={() => setActive(null)}>All</button>
        {store.categories.map((c) => (
          <button key={c} onClick={() => setActive(c)}>{c}</button>
        ))}
      </nav>
    </div>
  )
}
