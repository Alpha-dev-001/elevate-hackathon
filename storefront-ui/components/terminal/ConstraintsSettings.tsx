'use client'

import { useEffect, useState } from 'react'
import { api, ApiError } from '@/lib/api'
import type { Constraints } from '@/types/schemas'

/**
 * Merchant-facing view of BusinessConstraints — the interceptor's Layer 2
 * levers. GET/PUT /merchant/constraints already existed and were fully
 * wired end to end; this is the first UI that actually calls them. Qwen's
 * own discount proposals are always clamped to max_discount_percent
 * regardless of what this panel shows — this just lets the merchant see
 * and move that ceiling instead of it being an invisible default.
 */
export function ConstraintsSettings() {
  const [constraints, setConstraints] = useState<Constraints | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getConstraints()
      .then(setConstraints)
      .catch(() => setError('Could not load your settings'))
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    if (!constraints) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateConstraints({
        max_discount_percent: constraints.max_discount_percent,
        min_profit_margin_percent: constraints.min_profit_margin_percent,
        max_uplift_percent: constraints.max_uplift_percent,
      })
      setConstraints(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-xs text-muted font-mono">Loading settings…</p>
  if (!constraints) return <p className="text-xs text-danger font-mono">{error}</p>

  const inputCls =
    'bg-bg border border-border rounded-md px-3 py-2 text-text text-sm outline-none ' +
    'focus:border-accent transition-colors w-full'

  const row = (label: string, value: number, onChange: (n: number) => void) => (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs text-muted">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number" min={0} max={100} step={1}
          className={inputCls}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        />
        <span className="text-sm text-muted shrink-0">%</span>
      </div>
    </div>
  )

  return (
    <div className="card p-4 flex flex-col gap-4 w-full">
      <div>
        <p className="font-mono text-xs text-accent uppercase tracking-widest mb-1">Discount &amp; pricing limits</p>
        <p className="text-xs text-muted leading-relaxed">
          Qwen&apos;s own proposals are always clamped to these — nothing it suggests can go past what you set here.
        </p>
      </div>

      {row('Max discount Qwen can ever propose', constraints.max_discount_percent ?? 0,
        (n) => setConstraints({ ...constraints, max_discount_percent: n }))}
      {row('Minimum profit margin to protect', constraints.min_profit_margin_percent ?? 0,
        (n) => setConstraints({ ...constraints, min_profit_margin_percent: n }))}
      {row('Max price increase above baseline', constraints.max_uplift_percent,
        (n) => setConstraints({ ...constraints, max_uplift_percent: n }))}

      {error && <p className="text-danger text-xs font-mono">{error}</p>}
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="bg-accent text-bg font-semibold rounded-md py-2 px-4 text-sm hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {saving ? 'Saving…' : 'Save settings'}
        </button>
        {saved && <span className="text-xs font-mono" style={{ color: 'var(--color-accent)' }}>✦ Saved</span>}
      </div>
    </div>
  )
}
