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
type Issue = 'no-image' | 'broken-image' | 'missing-price' | 'uncertain-identity'
type Flag = { product: Product; issues: Issue[] }

const ISSUE_LABEL: Record<Issue, string> = {
  'no-image': 'no image',
  'broken-image': "image won't load",
  'missing-price': 'missing price',
  'uncertain-identity': 'needs verification',
}

/**
 * Test whether an image URL loads, with a generous timeout. Used to catch dead
 * links the server can't see (a customer's browser would hit the same thing).
 */
function testImage(url: string, timeoutMs = 10000): Promise<boolean> {
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

/**
 * Batched image checks — process at most `batchSize` at a time to avoid
 * overwhelming the browser's connection pool (6–8 per origin). A 98-product
 * catalog with all images fired at once would timeout most of them; batching
 * gives each batch a fair shot at the network.
 */
async function testImageBatched(urls: string[], batchSize = 5): Promise<Map<string, boolean>> {
  const results = new Map<string, boolean>()
  for (let i = 0; i < urls.length; i += batchSize) {
    const batch = urls.slice(i, i + batchSize)
    const outcomes = await Promise.all(batch.map((u) => testImage(u)))
    batch.forEach((u, j) => results.set(u, outcomes[j]))
  }
  return results
}

async function analyze(products: Product[], uncertainIds: Set<string>): Promise<Flag[]> {
  const flags: Flag[] = []

  // Collect all URLs that need image testing (skip products with no URL).
  const urlsToTest = products
    .filter((p) => !!p.image_url)
    .map((p) => p.image_url as string)

  const imageResults = urlsToTest.length > 0
    ? await testImageBatched(urlsToTest)
    : new Map<string, boolean>()

  for (const p of products) {
    const issues: Issue[] = []
    if (uncertainIds.has(p.id)) issues.push('uncertain-identity')
    if (!p.image_url) {
      issues.push('no-image')
    } else if (!imageResults.get(p.image_url)) {
      issues.push('broken-image')
    }
    if (!p.price || p.price <= 0) issues.push('missing-price')
    if (issues.length) flags.push({ product: p, issues })
  }
  return flags
}

export function CatalogReview({
  products,
  uncertainIds = new Set(),
  onProductUpdated,
  onProductHidden,
}: {
  products: Product[]
  uncertainIds?: Set<string>
  onProductUpdated: (p: Product) => void
  onProductHidden: (id: string) => void
}) {
  const [flags, setFlags] = useState<Flag[]>([])
  const [checking, setChecking] = useState(false)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  // Re-run when product ids OR uncertainIds change.
  const key = products.map((p) => p.id).join(',')
  const lastKey = useRef('')

  useEffect(() => {
    if (products.length === 0) { setFlags([]); return }
    // Include uncertainIds size in the key so re-runs trigger when vision results arrive.
    const compositeKey = `${key}|u:${uncertainIds.size}`
    if (compositeKey === lastKey.current) return
    lastKey.current = compositeKey
    let cancelled = false
    setChecking(true)
    analyze(products, uncertainIds).then((f) => {
      if (cancelled) return
      setFlags(f.filter((x) => !dismissed.has(x.product.id)))
      setChecking(false)
    })
    return () => { cancelled = true }
  }, [key, products, dismissed, uncertainIds])

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
  const needsIdentity = issues.includes('uncertain-identity')

  // Identity editors — pre-filled with current values so the merchant only
  // changes what's wrong, not re-types everything.
  const [editName, setEditName] = useState(product.name)
  const [editCategory, setEditCategory] = useState(product.category || '')
  const [editPrice, setEditPrice] = useState(product.price ? String(product.price) : '')

  const applyFix = async () => {
    setErr(null)
    const body: Record<string, unknown> = {}
    if (needsIdentity) {
      if (editName.trim() && editName.trim() !== product.name) body.name = editName.trim()
      if (editPrice.trim()) {
        const n = parseFloat(editPrice)
        if (!Number.isNaN(n) && n > 0) body.price = n
      }
      if (editCategory.trim() && editCategory.trim() !== product.category) body.category = editCategory.trim()
    }
    if (needsImage && imageUrl.trim()) body.image_url = imageUrl.trim()
    if (needsPrice && !needsIdentity && price.trim()) {
      const n = parseFloat(price)
      if (Number.isNaN(n) || n <= 0) { setErr('Enter a valid price.'); return }
      body.price = n
    }
    if (Object.keys(body).length === 0) { setErr('Add a fix first, or hide/keep.'); return }
    setBusy(true)
    try {
      const { product: updated } = await api.updateProduct(product.id, body as any)
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
      // Hard-delete, not a PATCH to is_active:false — these products are
      // already pending (is_active=false), so a PATCH to the same value is
      // a no-op that leaves a permanent zombie entry: it never resurfaces
      // here again, but it's still returned by every "pending approval"
      // surface (the products page, the terminal) forever, since nothing
      // ever removed it. DELETE matches the backend's own documented
      // semantics for a never-approved product (hard-delete, no orders
      // reference it).
      await api.deleteProduct(product.id)
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

      {needsIdentity && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-mono" style={{ color: 'var(--color-warning)' }}>
            Qwen wasn&apos;t sure about this product — verify the name and details.
          </p>
          <input className={inputCls} placeholder="Product name" value={editName}
                 onChange={(e) => setEditName(e.target.value)} />
          <div className="flex gap-2">
            <input className={`${inputCls} sm:max-w-[140px]`} placeholder="Price" inputMode="decimal"
                   value={editPrice} onChange={(e) => setEditPrice(e.target.value)} />
            <input className={inputCls} placeholder="Category" value={editCategory}
                   onChange={(e) => setEditCategory(e.target.value)} />
          </div>
        </div>
      )}

      {(needsImage || needsPrice) && (
        <div className="flex flex-col sm:flex-row gap-2">
          {needsImage && (
            <input className={inputCls} placeholder="Paste a working image URL" value={imageUrl}
                   onChange={(e) => setImageUrl(e.target.value)} />
          )}
          {needsPrice && !needsIdentity && (
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
