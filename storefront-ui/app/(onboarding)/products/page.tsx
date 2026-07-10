'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import { parseProductCsv } from '@/lib/csv'
import { useStore } from '@/lib/store'
import { ProductImage } from '@/components/storefront/ProductImage'
import { CatalogReview } from '@/components/onboarding/CatalogReview'
import { ImageDropZone } from '@/components/onboarding/ImageDropZone'
import type { Product, DeduplicateReport, CatalogAuditReport } from '@/types/schemas'

/**
 * Step 4 — inventory. Add products one at a time, drop a CSV, or drop product
 * photos (qwen-vl-max identifies each product from the image). Descriptions are
 * written in one batched qwen-max call (CSV/manual) or by the vision pipeline
 * (photo drop). Publish from here. Zero products is allowed — the store opens
 * in its "preparing the shelves" state.
 */
export default function ProductsPage() {
  const router = useRouter()
  const { storeShellUrl, liveUrl } = useStore()
  const setLiveUrl = useStore((s) => s.setLiveUrl)
  const csvInput = useRef<HTMLInputElement>(null)

  const [products, setProducts] = useState<Product[]>([])
  const [pendingProducts, setPendingProducts] = useState<Product[]>([])
  const [form, setForm] = useState({ name: '', price: '', cost_price: '', stock: '', category: '', image_url: '' })
  const [adding, setAdding] = useState(false)
  const [csvBusy, setCsvBusy] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [uncertainIds, setUncertainIds] = useState<Set<string>>(new Set())
  const [dedupReport, setDedupReport] = useState<DeduplicateReport | null>(null)
  const [auditReport, setAuditReport] = useState<CatalogAuditReport | null>(null)
  const [auditing, setAuditing] = useState(false)

  useEffect(() => {
    api.listProducts().then(setProducts).catch(() => {})
    api.listPendingProducts().then(setPendingProducts).catch(() => {})
    // Auto-deduplicate on page load — catches any Qwen-generated duplicates silently
    api.deduplicateProducts().then(setDedupReport).catch(() => {})
  }, [])

  const handleVisionProducts = useCallback((newProducts: Product[], uncertain: string[]) => {
    // Vision products start as pending — merchant approves each one
    setPendingProducts((prev) => [...prev, ...newProducts])
    if (uncertain.length > 0) {
      setUncertainIds((prev) => new Set([...prev, ...uncertain]))
    }
  }, [])

  const approveProduct = useCallback(async (p: Product) => {
    try {
      const approved = await api.approveProduct(p.id)
      setPendingProducts((prev) => prev.filter((x) => x.id !== p.id))
      setProducts((prev) => [...prev, approved])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not approve product')
    }
  }, [])

  const [approvingAll, setApprovingAll] = useState(false)
  const approveAll = useCallback(async () => {
    setApprovingAll(true)
    try {
      const approved = await api.approveAllProducts()
      setPendingProducts([])
      setProducts((prev) => [...prev, ...approved])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not approve all')
    } finally {
      setApprovingAll(false)
    }
  }, [])

  const discardPending = useCallback(async (id: string) => {
    try {
      await api.deleteProduct(id)
      setPendingProducts((prev) => prev.filter((x) => x.id !== id))
    } catch {
      setError('Could not discard product')
    }
  }, [])

  const addSingle = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const price = parseFloat(form.price)
    const cost = parseFloat(form.cost_price)
    const stock = parseInt(form.stock, 10)
    if (!form.name || Number.isNaN(price) || Number.isNaN(cost) || Number.isNaN(stock)) {
      setError('Name, price, cost, and stock are required.')
      return
    }
    setAdding(true)
    try {
      const p = await api.addProduct({
        name: form.name, price, cost_price: cost, stock,
        category: form.category || undefined, image_url: form.image_url || undefined,
      })
      setProducts((prev) => [...prev, p])
      setForm({ name: '', price: '', cost_price: '', stock: '', category: '', image_url: '' })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add product')
    } finally {
      setAdding(false)
    }
  }

  const handleCsv = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    setNote(null)
    const text = await file.text()
    const { rows, skipped } = parseProductCsv(text)
    if (!rows.length) {
      setError('No valid rows found. Columns: name, price, stock, image_url, category.')
      return
    }
    setCsvBusy(true)
    try {
      const created = await api.addProductsBatch(rows)
      setProducts((prev) => [...prev, ...created])
      setNote(`Added ${created.length} product${created.length > 1 ? 's' : ''}` + (skipped ? `, skipped ${skipped} invalid row${skipped > 1 ? 's' : ''}.` : '.'))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'CSV import failed')
    } finally {
      setCsvBusy(false)
      if (csvInput.current) csvInput.current.value = ''
    }
  }

  const publish = async () => {
    setError(null)
    setPublishing(true)
    try {
      const res = await api.publish()
      setLiveUrl(res.storefront_url)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Publish failed')
    } finally {
      setPublishing(false)
    }
  }

  const inputCls =
    'bg-bg border border-border rounded-md px-3 py-2.5 text-text text-sm ' +
    'outline-none focus:border-accent transition-colors placeholder:text-muted'

  return (
    <main className="min-h-screen flex flex-col items-center p-6 py-14 gap-8">
      <div className="w-full max-w-2xl">
        <p className="font-mono text-xs text-accent uppercase tracking-widest mb-1">The inventory</p>
        <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: 'var(--font-display)' }}>
          Add your products
        </h1>
        <p className="text-muted text-sm mt-1">Qwen writes each description in your brand voice.</p>
      </div>

      {/* single add */}
      <form onSubmit={addSingle} className="card w-full max-w-2xl p-5 grid grid-cols-2 gap-3">
        <input className={`${inputCls} col-span-2`} placeholder="Product name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className={inputCls} placeholder="Price" inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
        <input className={inputCls} placeholder="Cost price" inputMode="decimal" value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} />
        <input className={inputCls} placeholder="Stock" inputMode="numeric" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />
        <input className={inputCls} placeholder="Category (optional)" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
        <input className={`${inputCls} col-span-2`} placeholder="Image URL (optional)" value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} />
        <button type="submit" disabled={adding} className="col-span-2 bg-accent text-bg font-semibold rounded-md py-2.5 text-sm hover:opacity-90 disabled:opacity-50 transition-opacity">
          {adding ? 'Qwen is writing…' : 'Add product'}
        </button>
      </form>

      {/* CSV drop */}
      <div className="w-full max-w-2xl">
        <div
          onClick={() => csvInput.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); handleCsv(e.dataTransfer.files?.[0]) }}
          className="cursor-pointer rounded-lg border-2 border-dashed border-border hover:border-accent transition-colors p-5 text-center"
        >
          <p className="text-sm text-text">{csvBusy ? 'Importing…' : 'Or drop a CSV'}</p>
          <p className="text-muted text-xs font-mono mt-1">columns: name, price, stock, image_url, category</p>
        </div>
        <input ref={csvInput} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => handleCsv(e.target.files?.[0])} />
        {note && <p className="text-accent text-xs font-mono mt-2">{note}</p>}
      </div>

      {/* Photo drop — qwen-vl-max identifies each product from the photo */}
      <ImageDropZone onProductsCreated={handleVisionProducts} />

      {/* Dedup report — auto-merged duplicates + merchant-written duplicates for review */}
      {dedupReport && dedupReport.total_duplicates > 0 && (
        <div className="w-full max-w-2xl rounded-xl border border-neutral-800 p-4" style={{ background: 'var(--color-surface, #111113)' }}>
          <p className="font-mono text-xs text-warning uppercase tracking-widest mb-1">Catalog Cleanup</p>
          <p className="text-sm text-muted mb-3">
            Found {dedupReport.total_duplicates} duplicate{dedupReport.total_duplicates !== 1 ? 's' : ''} across {dedupReport.total_scanned} products.
          </p>
          {dedupReport.auto_merged.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-accent mb-1">✓ Auto-merged {dedupReport.auto_merged.length} Qwen-generated duplicate{dedupReport.auto_merged.length !== 1 ? 's' : ''}</p>
              {dedupReport.auto_merged.map((g, i) => (
                <p key={i} className="text-xs text-muted ml-3">
                  Kept &ldquo;{g.names[0]}&rdquo; — removed {g.product_ids.length - 1} duplicate{g.product_ids.length - 1 !== 1 ? 's' : ''}
                </p>
              ))}
            </div>
          )}
          {dedupReport.needs_review.length > 0 && (
            <div>
              <p className="text-xs text-warning mb-1">⚠ {dedupReport.needs_review.length} merchant-written duplicate{dedupReport.needs_review.length !== 1 ? 's' : ''} — please review</p>
              {dedupReport.needs_review.map((g, i) => (
                <div key={i} className="flex items-center gap-2 ml-3 text-xs text-muted">
                  <span>{g.names.join(', ')}</span>
                  <button
                    onClick={async () => {
                      // Discard all but the first product in the group
                      for (const id of g.product_ids.slice(1)) {
                        try {
                          await api.deleteProduct(id)
                          setProducts((prev) => prev.filter((p) => p.id !== id))
                        } catch { /* ignore */ }
                      }
                      setDedupReport((prev) => prev ? {
                        ...prev,
                        needs_review: prev.needs_review.filter((_, j) => j !== i),
                      } : null)
                    }}
                    className="text-danger hover:text-red-400 underline"
                  >
                    Remove duplicates
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Product Vision — pending products awaiting merchant approval */}
      {pendingProducts.length > 0 && (
        <div className="w-full max-w-2xl flex flex-col gap-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-xs text-accent uppercase tracking-widest mb-1">Product Vision</p>
              <p className="text-sm text-muted">
                Qwen identified {pendingProducts.length} product{pendingProducts.length !== 1 ? 's' : ''} from your photos.
                Approve each to add it to your store.
              </p>
            </div>
            <button
              onClick={approveAll}
              disabled={approvingAll}
              className="shrink-0 bg-accent text-bg font-semibold rounded-md py-2 px-4 text-xs hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {approvingAll ? 'Approving…' : `Approve all (${pendingProducts.length})`}
            </button>
          </div>
          <AnimatePresence>
            {pendingProducts.map((p) => (
              <motion.div
                key={p.id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -40, transition: { duration: 0.25 } }}
                transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                className="card p-4 flex gap-4 items-start"
                style={{ borderColor: 'color-mix(in srgb, var(--color-accent) 30%, var(--color-border))' }}
              >
                <div className="w-14 h-14 rounded-md overflow-hidden bg-surface-2 shrink-0">
                  <ProductImage src={p.image_url} alt={p.name} initial={p.name} className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-text font-semibold truncate">{p.name}</p>
                    <span className="text-accent font-mono text-sm">${p.price}</span>
                    {p.category && (
                      <span className="text-[10px] font-mono text-muted border border-border rounded-full px-1.5 py-0.5">{p.category}</span>
                    )}
                    {uncertainIds.has(p.id) && (
                      <span className="text-[10px] font-mono rounded-full px-1.5 py-0.5"
                            style={{ background: 'color-mix(in srgb, var(--color-warning) 18%, transparent)', color: 'var(--color-warning)' }}>
                        needs verification
                      </span>
                    )}
                  </div>
                  {p.description && <p className="text-sm text-muted mt-1 leading-relaxed">{p.description}</p>}
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => approveProduct(p)}
                      className="bg-accent text-bg font-semibold rounded-md py-1.5 px-4 text-xs hover:opacity-90 transition-opacity"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => discardPending(p.id)}
                      className="rounded-md py-1.5 px-3 text-xs border border-border text-muted hover:text-danger hover:border-danger transition-colors"
                    >
                      Discard
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {error && <p className="text-danger text-sm font-mono max-w-2xl w-full">{error}</p>}

      {/* Qwen reviews the import and surfaces only the products that need a human
          decision — fix, hide, or keep. */}
      <CatalogReview
        products={products}
        uncertainIds={uncertainIds}
        onProductUpdated={(p) => setProducts((prev) => prev.map((x) => (x.id === p.id ? p : x)))}
        onProductHidden={(id) => setProducts((prev) => prev.filter((x) => x.id !== id))}
      />

      {/* Qwen Catalog Audit — one-click AI review */}
      {products.length > 0 && (
        <div className="w-full max-w-2xl flex flex-col gap-3">
          <button
            onClick={async () => {
              setAuditing(true)
              try {
                const report = await api.catalogAudit()
                setAuditReport(report)
              } catch (err) {
                setError(err instanceof ApiError ? err.message : 'Catalog audit failed')
              } finally {
                setAuditing(false)
              }
            }}
            disabled={auditing}
            className="self-start text-xs font-medium py-2 px-4 rounded-lg border border-neutral-700 hover:border-emerald-400/60 disabled:opacity-40 transition-colors"
          >
            {auditing ? (
              <span className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                Qwen is auditing…
              </span>
            ) : '✦ Run Qwen catalog audit'}
          </button>

          {auditReport && (
            <div className="rounded-xl border border-neutral-800 p-4" style={{ background: 'var(--color-surface, #111113)' }}>
              <div className="flex items-center justify-between mb-2">
                <p className="font-mono text-xs uppercase tracking-widest" style={{ color: auditReport.catalog_score >= 80 ? 'var(--color-accent, #6EE7B7)' : auditReport.catalog_score >= 50 ? 'var(--color-warning, #FFD166)' : 'var(--color-danger, #FF6B6B)' }}>
                  Catalog Score: {auditReport.catalog_score}/100
                </p>
                <button onClick={() => setAuditReport(null)} className="text-xs text-muted hover:text-white">×</button>
              </div>
              <p className="text-sm text-muted mb-3">{auditReport.summary}</p>
              {auditReport.findings.length === 0 ? (
                <p className="text-xs text-accent">✓ No issues found — your catalog looks clean.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {auditReport.findings.map((f, i) => (
                    <div key={i} className="text-xs border-l-2 pl-3 py-1"
                         style={{ borderColor: f.severity === 'high' ? 'var(--color-danger, #FF6B6B)' : f.severity === 'medium' ? 'var(--color-warning, #FFD166)' : '#555' }}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">{f.product_name}</span>
                        <span className="text-muted px-1.5 py-0.5 rounded-full text-[10px]" style={{ background: '#1A1A1E' }}>
                          {f.issue_type.replace('_', ' ')}
                        </span>
                      </div>
                      <p className="text-muted mt-0.5">{f.description}</p>
                      <p className="text-accent mt-0.5">→ {f.suggested_fix}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* product list */}
      {products.length > 0 && (
        <div className="w-full max-w-2xl flex flex-col gap-3">
          <AnimatePresence>
            {products.map((p) => (
              <motion.div
                key={p.id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                className="card p-4 flex gap-4 items-start"
              >
                {/* Always render via ProductImage: a dead/missing URL falls back
                    to a branded initial tile instead of a broken-image glyph —
                    keeps the add screen clean on camera. */}
                <div className="w-14 h-14 rounded-md overflow-hidden bg-surface-2 shrink-0">
                  <ProductImage src={p.image_url} alt={p.name} initial={p.name} className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-text font-semibold truncate">{p.name}</p>
                    <span className="text-accent font-mono text-sm">${p.price}</span>
                    {p.qwen_generated && (
                      <span className="text-[10px] font-mono text-muted border border-border rounded-full px-1.5 py-0.5">qwen</span>
                    )}
                  </div>
                  {p.description && <p className="text-sm text-muted mt-1 leading-relaxed">{p.description}</p>}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* publish */}
      <div className="w-full max-w-2xl flex flex-col items-center gap-3 mt-2">
        {liveUrl ? (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="card w-full p-6 text-center border-accent">
            <p className="font-mono text-xs text-accent uppercase tracking-widest mb-2">Live</p>
            <p className="text-text mb-1">Your store is live.</p>
            <p className="text-muted text-xs mb-3">Approved products sync to the storefront instantly.</p>
            <a href={liveUrl} className="text-accent font-mono text-sm underline underline-offset-4 break-all">{storeShellUrl ?? liveUrl}</a>
          </motion.div>
        ) : (
          <>
            <button onClick={publish} disabled={publishing || !products.length} className="bg-accent text-bg font-semibold rounded-md py-3 px-10 text-sm hover:opacity-90 disabled:opacity-50 transition-opacity accent-glow">
              {publishing ? 'Publishing…' : `Publish store${products.length ? ` (${products.length})` : ''} →`}
            </button>
            {!products.length && pendingProducts.length > 0 && (
              <p className="text-muted text-xs font-mono">Approve products first to publish.</p>
            )}
            <button onClick={() => router.push('/brand-review')} className="text-muted text-xs font-mono hover:text-accent transition-colors">
              ← back to brand
            </button>
            <button onClick={() => router.push('/terminal')} className="text-muted text-xs font-mono hover:text-accent transition-colors">
              ← terminal
            </button>
          </>
        )}
      </div>
    </main>
  )
}
