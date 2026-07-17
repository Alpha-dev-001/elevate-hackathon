'use client'

import { useEffect, useState } from 'react'
import { api, type SearchInsight } from '@/lib/api'

/** Slugs ("winter-boots") → "winter boots" for display, matching
 * CapabilityProposals' humanize() convention. */
function humanize(label: string): string {
  return (label || '').replace(/[-_]+/g, ' ').trim()
}

const MAX_SHOWN = 10

/**
 * Store-wide search demand — every query a customer typed into the
 * storefront search box (see SearchBar.tsx → POST /api/store/{slug}/search),
 * aggregated. Unmatched queries (nothing in the catalog matched) are the
 * highest-signal row: real demand for a product the store doesn't carry.
 * Self-fetching like DecisionLog — reference data, not something the page's
 * WS pipeline needs to push live.
 */
export function SearchDemandInsights({ slug }: { slug: string }) {
  const [searches, setSearches] = useState<SearchInsight[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api.getSearchInsights(slug).then((res) => {
      if (!cancelled) {
        setSearches(res.searches)
        setLoading(false)
      }
    }).catch(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [slug])

  if (loading) return null

  const unmatchedCount = searches.filter((s) => !s.matched).length

  return (
    <section
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
    >
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span
          className="text-sm font-semibold"
          style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
        >
          Search demand
        </span>
        {unmatchedCount > 0 && (
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0"
            style={{ background: 'rgba(255,107,107,0.12)', color: 'var(--color-danger)' }}
          >
            {unmatchedCount} unmet
          </span>
        )}
      </div>
      <p className="text-xs font-mono mb-3" style={{ color: 'var(--color-text-muted)' }}>
        What customers type into your search box, most-searched first.
      </p>

      {searches.length === 0 ? (
        <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
          No searches logged yet — this fills in as customers use the storefront search box.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {searches.slice(0, MAX_SHOWN).map((s) => (
            <li
              key={s.query}
              className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-2)' }}
            >
              <span className="text-sm truncate" style={{ color: 'var(--color-text)' }} title={s.label}>
                {humanize(s.label)}
              </span>
              <span className="flex items-center gap-2 shrink-0">
                {!s.matched && (
                  <span
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(255,107,107,0.12)', color: 'var(--color-danger)' }}
                  >
                    not in catalog
                  </span>
                )}
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={{
                    background: 'var(--color-accent-dim, rgba(110,231,183,0.12))',
                    color: 'var(--color-accent)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {s.count}×
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
