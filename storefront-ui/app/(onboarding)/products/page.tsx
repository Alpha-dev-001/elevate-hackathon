'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import { parseProductCsv } from '@/lib/csv'
import { useStore } from '@/lib/store'
import type { Product } from '@/types/schemas'

/**
 * Step 4 — inventory. Add products one at a time or drop a CSV; qwen-max writes
 * each description (one batched call) and they flow into the list. Publish from
 * here. Zero products is allowed — the store opens in its "preparing the
 * shelves" state.
 */
export default function ProductsPage() {
  const router = useRouter()
  const { storeShellUrl, liveUrl } = useStore()
  const setLiveUrl = useStore((s) => s.setLiveUrl)
  const csvInput = useRef<HTMLInputElement>(null)

  const [products, setProducts] = useState<Product[]>([])
  const [form, setForm] = useState({ name: '', price: '', cost_price: '', stock: '', category: '', image_url: '' })
  const [adding, setAdding] = useState(false)
  const [csvBusy, setCsvBusy] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    api.listProducts().then(setProducts).catch(() => {})
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

      {error && <p className="text-danger text-sm font-mono max-w-2xl w-full">{error}</p>}

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
                {p.image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.image_url} alt={p.name} className="w-14 h-14 rounded-md object-cover bg-surface-2 shrink-0" />
                )}
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
            <p className="text-text mb-3">Your store is live.</p>
            <a href={liveUrl} className="text-accent font-mono text-sm underline underline-offset-4 break-all">{storeShellUrl ?? liveUrl}</a>
          </motion.div>
        ) : (
          <>
            <button onClick={publish} disabled={publishing} className="bg-accent text-bg font-semibold rounded-md py-3 px-10 text-sm hover:opacity-90 disabled:opacity-50 transition-opacity accent-glow">
              {publishing ? 'Publishing…' : `Publish store${products.length ? ` (${products.length})` : ''} →`}
            </button>
            <button onClick={() => router.push('/brand-review')} className="text-muted text-xs font-mono hover:text-accent transition-colors">
              ← back to brand
            </button>
          </>
        )}
      </div>
    </main>
  )
}
