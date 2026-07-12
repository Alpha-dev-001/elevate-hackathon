'use client'
import type { NavProps } from '@/lib/dslRegistry'

export function StickyTabsNav({ store, activeCategory, onSelect }: NavProps) {
  const items: (string | null)[] = [null, ...store.categories]
  return (
    <nav className="nav-links sticky top-0 z-20 flex gap-1 overflow-x-auto px-3 py-2 text-sm"
         style={{ background: 'var(--s-bg)', borderBottom: '1px solid color-mix(in srgb, var(--s-text) 10%, transparent)' }}>
      {items.map((c) => {
        const active = activeCategory === c
        return (
          <button key={c ?? 'all'} onClick={() => onSelect(c)}
                  className="nav-link relative whitespace-nowrap px-3 py-1.5"
                  style={{
                    background: active ? 'var(--s-surface)' : 'transparent',
                    color: active ? 'var(--s-text)' : 'var(--s-text-muted)',
                  }}>
            {c ?? 'All'}
            {active && <span className="absolute left-0 bottom-0 h-0.5 w-full" style={{ background: 'var(--s-accent)' }} />}
          </button>
        )
      })}
    </nav>
  )
}
