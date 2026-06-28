'use client'
import type { NavProps } from '@/lib/dslRegistry'

export function PillNav({ store, activeCategory, onSelect }: NavProps) {
  const items: (string | null)[] = [null, ...store.categories]
  return (
    <nav className="flex gap-2 overflow-x-auto px-5 md:px-10 py-4 text-sm">
      {items.map((c) => {
        const active = activeCategory === c
        return (
          <button key={c ?? 'all'} onClick={() => onSelect(c)}
                  className="whitespace-nowrap px-4 py-1.5 rounded-full transition-colors"
                  style={
                    active
                      ? { background: 'var(--s-accent)', color: 'var(--s-bg)' }
                      : { color: 'var(--s-text-muted)', border: '1px solid color-mix(in srgb, var(--s-text) 18%, transparent)' }
                  }>
            {c ?? 'All'}
          </button>
        )
      })}
    </nav>
  )
}
