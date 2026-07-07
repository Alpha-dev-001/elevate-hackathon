'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import type { Product } from '@/types/schemas'

/**
 * Catalog review — the autopilot's human-in-the-loop beat for onboarding.
 *
 * Qwen catalogs your products; this step has it *review* what came in and surface
 * only the ones a human should look at: an image that won't load, a dead link, a
 * missing price. Each is an option card — fix it inline, hide it from the store,
 * or keep it anyway. Nothing is auto-changed; the merchant decides.
 *
 * Broken-image detection runs in the browser (a real load test), so it catches
 * dead links the server never sees — and it's exactly what a customer's browser
 * would hit, so a clean review means a clean storefront.
 */
type Issue = 'no-image' | 'broken-image' | 'missing-price'
type Flag = { product: Product; issues: Issue[] }

const ISSUE_LABEL: Record<Issue, string> = {
  'no-image': 'no image',
  'broken-image': "image won't load",
  'missing-price': 'missing price',
}

function testImage(url: string, timeoutMs = 6000): Promise<boolean> {
  return new Promise((resolve) => {
    if (!url) return resolve(false)
    const img = new Image()
    let done = false
    const finish = (ok: boolean) => { if (!done) { done = true; resolve(ok) } }
    img.onload = () => finish(true)
    img.onerror = () => finish(false)
    setTimeout(() => finish(false), timeoutMs)
    img.src = url
  })
}

async function analyze(products: Product[]): Promise<Flag[]> {
  const flags: Flag[] = []
  await Promise.all(
    products.map(async (p) => {
      const issues: Issue[] = []
      if (!p.image_url) issues.push('no-image')
      else if (!(await testImage(p.image_url))) issues.push('broken-image')
      if (!p.price || p.price <= 0) issues.push('missing-price')
      if (issues.length) flags.push({ product: p, issues })
    }),
  )
  return flags
}

export function CatalogReview({
  products,
  onProductUpdated,
  onProductHidden,
}: {
  products: Product[]
  onProductUpdated: (p: Product) => void
  onProductHidden: (id: string) => void
}) {
  const [flags, setFlags] = useState<Flag[]>([])
  const [checking, setChecking] = useState(false)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  // Re-run only when the set of product ids changes, not on every render.
  const key = products.map((p) => p.id).join(',')
  const lastKey = useRef('')

  useEffect(() => {
    if (products.length === 0) { setFlags([]); return }
    if (key === lastKey.current) return
    lastKey.current = key
    let cancelled = false
    setChecking(true)
    analyze(products).then((f) => {
      if (cancelled) return
      setFlags(f.filter((x) => !dismissed.has(x.product.id)))
      setChecking(false)
    })
    return () => { cancelled = true }
  }, [key, products, dismissed])

  const visible = flags.filter((f) => !dismissed.has(f.product.id))
  if (checking && visible.length === 0) {
    return (
      <div className="w-full max-w-2xl">
        <p className="font-mono text-xs text-muted flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          Qwen is reviewing your catalog…
        </p>
      </div>
    )
  }
  if (visible.length === 0) return null

  return (
    <div className="w-full max-w-2xl flex flex-col gap-3">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-1" style={{ color: 'var(--color-warning)' }}>
          Catalog review · {visible.length}
        </p>
        <p className="text-sm text-muted">
          Qwen catalogued your products and flagged{' '}
          <span className="text-text font-medium">{visible.length}</span> that need your eye before you publish.
          Fix, hide, or keep — your call.
        </p>
      </div>
      <AnimatePresence>
        {visible.map((f) => (
          <ReviewCard
            key={f.product.id}
            flag={f}
            onUpdated={(p) => { onProductUpdated(p); lastKey.current = '' }}
            onHidden={(id) => { setDismissed((s) => new Set(s).add(id)); onProductHidden(id) }}
            onKeep={(id) => setDismissed((s) => new Set(s).add(id))}
          />
        ))}
      </AnimatePresence>
    </div>
  )
}

function ReviewCard({
  flag, onUpdated, onHidden, onKeep,
}: {
  flag: Flag
  onUpdated: (p: Product) => void
  onHidden: (id: string) => void
  onKeep: (id: string) => void
}) {
  const { product, issues } = flag
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState('')
  const [price, setPrice] = useState('')
  const needsImage = issues.includes('no-image') || issues.includes('broken-image')
  const needsPrice = issues.includes('missing-price')

  const applyFix = async () => {
    setErr(null)
    const body: { image_url?: string; price?: number } = {}
    if (needsImage && imageUrl.trim()) body.image_url = imageUrl.trim()
    if (needsPrice && price.trim()) {
      const n = parseFloat(price)
      if (Number.isNaN(n) || n <= 0) { setErr('Enter a valid price.'); return }
      body.price = n
    }
    if (Object.keys(body).length === 0) { setErr('Add a fix first, or hide/keep.'); return }
    setBusy(true)
    try {
      const { product: updated } = await api.updateProduct(product.id, body)
      onUpdated(updated)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const hide = async () => {
    setBusy(true); setErr(null)
    try {
      await api.updateProduct(product.id, { is_active: false })
      onHidden(product.id)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not hide')
      setBusy(false)
    }
  }

  const inputCls =
    'bg-bg border border-border rounded-md px-3 py-2 text-text text-sm outline-none ' +
    'focus:border-accent transition-colors placeholder:text-muted w-full'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }}
      transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
      className="card p-4 flex flex-col gap-3"
      style={{ borderColor: 'color-mix(in srgb, var(--color-warning) 40%, var(--color-border))' }}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-text font-semibold truncate">{product.name}</p>
        {issues.map((i) => (
          <span key={i} className="text-[10px] font-mono rounded-full px-1.5 py-0.5"
                style={{ background: 'color-mix(in srgb, var(--color-warning) 18%, transparent)', color: 'var(--color-warning)' }}>
            {ISSUE_LABEL[i]}
          </span>
        ))}
      </div>

      {(needsImage || needsPrice) && (
        <div className="flex flex-col sm:flex-row gap-2">
          {needsImage && (
            <input className={inputCls} placeholder="Paste a working image URL" value={imageUrl}
                   onChange={(e) => setImageUrl(e.target.value)} />
          )}
          {needsPrice && (
            <input className={`${inputCls} sm:max-w-[140px]`} placeholder="Price" inputMode="decimal" value={price}
                   onChange={(e) => setPrice(e.target.value)} />
          )}
        </div>
      )}

      {err && <p className="text-danger text-xs font-mono">{err}</p>}

      <div className="flex gap-2 flex-wrap">
        <button onClick={applyFix} disabled={busy}
                className="bg-accent text-bg font-semibold rounded-md py-2 px-4 text-sm hover:opacity-90 disabled:opacity-50 transition-opacity">
          {busy ? 'Saving…' : 'Fix it'}
        </button>
        <button onClick={hide} disabled={busy}
                className="rounded-md py-2 px-4 text-sm border border-border text-muted hover:text-text hover:border-danger transition-colors disabled:opacity-50">
          Hide from store
        </button>
        <button onClick={() => onKeep(product.id)} disabled={busy}
                className="rounded-md py-2 px-4 text-sm text-muted hover:text-text transition-colors disabled:opacity-50">
          Keep anyway
        </button>
      </div>
    </motion.div>
  )
}
