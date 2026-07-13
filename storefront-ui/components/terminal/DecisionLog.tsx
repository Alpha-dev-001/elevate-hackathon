'use client'

import { useEffect, useState } from 'react'
import { api, type DecisionLogEntry } from '@/lib/api'

export function DecisionLog() {
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getDecisions().then((res) => {
      if (!cancelled) {
        setDecisions(res.decisions)
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
        <div
          key={d.id}
          className="p-4 rounded-lg"
          style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-sm font-bold" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
              {d.title}
            </h4>
            <span
              className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded"
              style={{ background: 'var(--color-border)', color: 'var(--color-text-muted)' }}
            >
              {d.status}
            </span>
          </div>
          <p className="text-xs font-mono mb-1" style={{ color: 'var(--color-warning)' }}>
            {d.trigger}
          </p>
          <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
            {d.description}
          </p>
        </div>
      ))}
    </div>
  )
}
