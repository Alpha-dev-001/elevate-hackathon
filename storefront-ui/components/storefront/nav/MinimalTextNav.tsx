'use client'
import type { NavProps } from '@/lib/dslRegistry'

export function MinimalTextNav({ store, activeCategory, onSelect }: NavProps) {
  const items: (string | null)[] = [null, ...store.categories]
  return (
    <nav className="flex flex-wrap gap-x-3 gap-y-1 px-5 md:px-10 py-4 text-sm">
      {items.map((c, i) => (
        <span key={c ?? 'all'} className="flex items-center gap-3">
          <button onClick={() => onSelect(c)}
                  className="transition-colors hover:opacity-80"
                  style={{ color: activeCategory === c ? 'var(--s-accent)' : 'var(--s-text-muted)' }}>
            {c ?? 'All'}
          </button>
          {i < items.length - 1 && <span aria-hidden style={{ color: 'var(--s-text-muted)' }}>,</span>}
        </span>
      ))}
    </nav>
  )
}
