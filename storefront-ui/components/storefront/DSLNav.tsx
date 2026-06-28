'use client'
import { useState } from 'react'
import type { PublicStore } from '@/types/schemas'
import { NAV_REGISTRY } from '@/lib/dslRegistry'

export function DSLNav({ store, navStyle }: { store: PublicStore; navStyle: string }) {
  const [active, setActive] = useState<string | null>(null)
  const Comp = NAV_REGISTRY[navStyle]
  if (Comp) {
    return (
      <div data-nav={navStyle}>
        <Comp store={store} activeCategory={active} onSelect={setActive} />
      </div>
    )
  }
  // Minimal inline fallback until the nav family lands (Task 14).
  return (
    <nav data-nav={navStyle} className="flex gap-3 px-5 py-3 text-sm">
      <button onClick={() => setActive(null)}>All</button>
      {store.categories.map((c) => (
        <button key={c} onClick={() => setActive(c)}>{c}</button>
      ))}
    </nav>
  )
}
