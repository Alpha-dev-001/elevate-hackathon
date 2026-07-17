'use client'
import { IconSearch, IconX } from '@/components/icons'

/**
 * Nav-style-agnostic — rendered once by DSLRenderer regardless of which
 * NAV_REGISTRY variant is active, instead of duplicated into every nav
 * variant component. Filtering itself is instant and owned by the parent
 * (DSLRenderer already has store.products in memory); this is just the
 * controlled input.
 */
export function SearchBar({
  value, onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="px-5 md:px-10 pb-3">
      <div
        className="flex items-center gap-2 px-3.5 py-2.5 rounded-full max-w-md"
        style={{ background: 'var(--s-surface)', border: '1px solid var(--s-border, rgba(0,0,0,0.1))' }}
      >
        <IconSearch size={16} style={{ color: 'var(--s-text-muted, var(--s-text))', opacity: 0.6, flexShrink: 0 }} />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search products…"
          aria-label="Search products"
          className="flex-1 bg-transparent outline-none text-sm min-w-0"
          style={{ color: 'var(--s-text)' }}
        />
        {value && (
          <button
            onClick={() => onChange('')}
            aria-label="Clear search"
            className="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity"
            style={{ color: 'var(--s-text)' }}
          >
            <IconX size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
