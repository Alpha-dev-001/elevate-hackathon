'use client'

import { useEffect, useState, useCallback } from 'react'
import { api, type DecisionLogEntry } from '@/lib/api'
import { connectTerminal } from '@/lib/ws'

const ROLE_LABELS: Record<string, string> = {
  pricing_strategist: 'Pricing Strategist',
  sales_rep: 'Sales Rep',
  inventory_overseer: 'Inventory Overseer',
  store_curator: 'Store Curator',
}

function DecisionRow({ d }: { d: DecisionLogEntry }) {
  const [showReasoning, setShowReasoning] = useState(false)
  const [showContext, setShowContext] = useState(false)
  const timeLabel = new Date(d.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
  const ctx = d.context_snapshot
  const hasContext = !!(ctx && (ctx.products_summary || ctx.memory_context || ctx.learned_stance || ctx.max_discount_percent != null))

  return (
    <div
      className="p-4 rounded-lg"
      style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}
    >
      <div className="flex items-center justify-between mb-1 gap-2">
        <h4 className="text-sm font-bold" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
          {d.title}
        </h4>
        <span className="flex items-center gap-2 shrink-0">
          {d.role && ROLE_LABELS[d.role] && (
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}
            >
              ✦ {ROLE_LABELS[d.role]}
            </span>
          )}
          <span
            className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded"
            style={{ background: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            {d.status}
          </span>
        </span>
      </div>
      <p className="text-[10px] font-mono mb-2" style={{ color: 'var(--color-text-muted)' }}>
        {timeLabel}
      </p>
      <p className="text-xs font-mono mb-1" style={{ color: 'var(--color-warning)' }}>
        {d.trigger}
      </p>
      <p className="text-sm mb-2" style={{ color: 'var(--color-text-muted)' }}>
        {d.description}
      </p>
      {d.reasoning && (
        <>
          <button
            onClick={() => setShowReasoning((s) => !s)}
            className="text-[10px] font-mono uppercase tracking-widest"
            style={{ color: showReasoning ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
          >
            {showReasoning ? '▾' : '▸'} ✦ why Qwen decided this
          </button>
          {showReasoning && (
            <p
              className="text-xs font-mono leading-relaxed mt-2 pl-3 border-l-2"
              style={{ color: 'var(--color-accent)', borderColor: 'var(--color-accent)', opacity: 0.85 }}
            >
              {d.reasoning}
            </p>
          )}
        </>
      )}
      {hasContext && (
        <div className={d.reasoning ? 'mt-2' : ''}>
          <button
            onClick={() => setShowContext((s) => !s)}
            className="text-[10px] font-mono uppercase tracking-widest"
            style={{ color: showContext ? 'var(--color-text)' : 'var(--color-text-muted)' }}
          >
            {showContext ? '▾' : '▸'} what Qwen was looking at
          </button>
          {showContext && (
            <div
              className="text-xs font-mono leading-relaxed mt-2 pl-3 border-l-2 flex flex-col gap-2"
              style={{ color: 'var(--color-text-muted)', borderColor: 'var(--color-border)' }}
            >
              {ctx.products_summary && (
                <div>
                  <span className="uppercase text-[10px] tracking-widest block mb-0.5" style={{ color: 'var(--color-text)' }}>
                    Catalog snapshot
                  </span>
                  {ctx.products_summary}
                </div>
              )}
              {ctx.memory_context && (
                <div>
                  <span className="uppercase text-[10px] tracking-widest block mb-0.5" style={{ color: 'var(--color-text)' }}>
                    Prior-outcome memory
                  </span>
                  <span className="whitespace-pre-wrap">{ctx.memory_context}</span>
                </div>
              )}
              {ctx.learned_stance && (
                <div className="pl-2 border-l-2" style={{ borderColor: 'var(--color-accent)' }}>
                  <span className="uppercase text-[10px] tracking-widest block mb-0.5" style={{ color: 'var(--color-accent)' }}>
                    ✦ Learned stance
                  </span>
                  <span className="whitespace-pre-wrap" style={{ color: 'var(--color-accent)', opacity: 0.9 }}>
                    {ctx.learned_stance}
                  </span>
                </div>
              )}
              {ctx.max_discount_percent != null && (
                <div>
                  <span className="uppercase text-[10px] tracking-widest block mb-0.5" style={{ color: 'var(--color-text)' }}>
                    Discount ceiling
                  </span>
                  {ctx.max_discount_percent}%
                  {ctx.avg_price != null && ` · catalog avg price $${ctx.avg_price}`}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const PAGE_SIZE = 20

interface DecisionLogProps {
  /** Opens a WS subscription so newly resolved decisions appear without a
   *  manual refresh — this page previously had none at all, so a decision
   *  resolved live (approve, dismiss, or an auto-applied trust move) never
   *  showed up here until the merchant reloaded. Optional so existing
   *  callers/tests that don't care about live updates keep working. */
  merchantId?: string
}

export function DecisionLog({ merchantId }: DecisionLogProps) {
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getDecisions(PAGE_SIZE, 0).then((res) => {
      if (!cancelled) {
        setDecisions(res.decisions)
        setTotal(res.total)
        setLoading(false)
      }
    }).catch(() => {
      if (!cancelled) {
        setError('Could not load decision history')
        setLoading(false)
      }
    })
    return () => { cancelled = true }
  }, [])

  // Re-fetch just the first page and merge in anything not already loaded,
  // by id — never discards pages the merchant already paged into via
  // "load more". Ordering is created_at DESC (newest first) server-side,
  // so new/updated rows always land in this first page.
  const refreshTop = useCallback(async () => {
    try {
      const res = await api.getDecisions(PAGE_SIZE, 0)
      setTotal(res.total)
      setDecisions((prev) => {
        // The fresh page-1 fetch always wins for any id it contains (an
        // entry can change status between fetches, e.g. pending -> executed)
        // — only entries beyond page 1 that the merchant paged into via
        // "load more" get preserved from the stale list.
        const freshIds = new Set(res.decisions.map((d) => d.id))
        const rest = prev.filter((d) => !freshIds.has(d.id))
        return [...res.decisions, ...rest]
      })
    } catch {
      // next event (or a manual reload) will retry — no error surfaced for
      // a background refresh the merchant didn't explicitly ask for
    }
  }, [])

  useEffect(() => {
    if (!merchantId) return
    const conn = connectTerminal(merchantId, {
      onEvent: (event) => {
        // Every path that resolves a decision (approve, dismiss, auto-apply)
        // already broadcasts state_updated — reusing it here means no new
        // backend event type is needed just for this page.
        if (event === 'state_updated') refreshTop()
      },
    })
    return () => conn.close()
  }, [merchantId, refreshTop])

  const loadMore = async () => {
    if (loadingMore) return
    setLoadingMore(true)
    try {
      const res = await api.getDecisions(PAGE_SIZE, decisions.length)
      setDecisions((prev) => [...prev, ...res.decisions])
      setTotal(res.total)
    } catch {
      // leave what's already loaded — the button just stays available to retry
    } finally {
      setLoadingMore(false)
    }
  }

  if (loading) return null

  if (error) {
    return (
      <p className="text-xs mb-3 font-mono" style={{ color: 'var(--color-danger)' }}>
        {error}
      </p>
    )
  }

  if (decisions.length === 0) {
    return (
      <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
        No decisions yet. Simulate activity or add a product to generate one.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {decisions.map((d) => (
        <DecisionRow key={d.id} d={d} />
      ))}
      {decisions.length < total && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          className="text-xs font-mono py-2 rounded-md border transition-opacity hover:opacity-80 disabled:opacity-50"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
        >
          {loadingMore ? 'Loading…' : `Load more (${decisions.length} of ${total})`}
        </button>
      )}
    </div>
  )
}
