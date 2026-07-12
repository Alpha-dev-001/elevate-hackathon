'use client'
import type { NavProps } from '@/lib/dslRegistry'

export function UnderlineTabsNav({ store, activeCategory, onSelect }: NavProps) {
  const items: (string | null)[] = [null, ...store.categories]
  return (
    <nav className="nav-links flex gap-6 overflow-x-auto px-5 md:px-10 py-4 text-sm">
      {items.map((c) => {
        const active = activeCategory === c
        return (
          <button key={c ?? 'all'} onClick={() => onSelect(c)}
                  className="nav-link relative whitespace-nowrap pb-1 transition-colors"
                  style={{ color: active ? 'var(--s-accent)' : 'var(--s-text-muted)' }}>
            {c ?? 'All'}
            <span className="absolute left-0 -bottom-0.5 h-0.5 w-full transition-opacity"
                  style={{ background: 'var(--s-accent)', opacity: active ? 1 : 0 }} />
          </button>
        )
      })}
    </nav>
  )
}
