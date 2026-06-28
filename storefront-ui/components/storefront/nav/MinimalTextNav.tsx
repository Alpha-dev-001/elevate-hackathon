'use client'
import { Fragment } from 'react'
import type { NavProps } from '@/lib/dslRegistry'

export function MinimalTextNav({ store, activeCategory, onSelect }: NavProps) {
  const items: (string | null)[] = [null, ...store.categories]
  return (
    <nav
      className="flex items-center gap-x-3 gap-y-0 overflow-x-auto whitespace-nowrap px-5 md:px-10 py-4 text-sm
                 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      aria-label="Categories"
    >
      {items.map((c, i) => (
        <Fragment key={c ?? 'all'}>
          {i > 0 && <span aria-hidden className="select-none opacity-30">/</span>}
          <button
            onClick={() => onSelect(c)}
            className="shrink-0 transition-colors hover:opacity-70"
            style={{
              color: activeCategory === c ? 'var(--s-accent)' : 'var(--s-text-muted)',
              fontWeight: activeCategory === c ? 500 : 400,
            }}
          >
            {c ?? 'All'}
          </button>
        </Fragment>
      ))}
    </nav>
  )
}
