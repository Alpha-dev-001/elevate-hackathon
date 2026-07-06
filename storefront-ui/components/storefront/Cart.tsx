'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import { useCart, getSessionId } from '@/lib/cart'
import { ProductImage } from '@/components/storefront/ProductImage'
import { PromoCountdown } from './PromoCountdown'
import type { Order } from '@/types/schemas'

/**
 * Slide-in cart drawer with inline checkout and order confirmation. Themed by
 * the store's CSS vars (inherited from the storefront <main>). Guest-first:
 * checkout only needs a name + email. Prices shown are the snapshots taken at
 * add-time — the backend honors them verbatim.
 */
type View = 'cart' | 'checkout' | 'done'
type CartVariant = 'slide-panel' | 'full-sheet'

export function Cart({ variant = 'slide-panel' }: { variant?: CartVariant } = {}) {
  const { cart, open, busy, error, slug, setOpen, setQty, remove } = useCart()
  const [view, setView] = useState<View>('cart')
  const [form, setForm] = useState({ name: '', email: '', note: '' })
  const [placing, setPlacing] = useState(false)
  const [checkoutErr, setCheckoutErr] = useState<string | null>(null)
  const [order, setOrder] = useState<Order | null>(null)

  const items = cart?.items ?? []
  const subtotal = cart?.subtotal ?? 0
  const discountPct = cart?.discount_percent ?? 0
  const discountAmt = cart?.discount_amount ?? 0
  const hasDiscount = discountPct > 0 && discountAmt > 0
  const total = hasDiscount ? (cart?.total ?? subtotal) : subtotal
  const close = () => {
    setOpen(false)
    // Reset to cart view next time it opens (unless an order is showing).
    if (view !== 'done') setView('cart')
  }

  const placeOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug) return
    setCheckoutErr(null)
    if (!form.name.trim() || !form.email.trim()) {
      setCheckoutErr('Name and email are required.')
      return
    }
    setPlacing(true)
    try {
      const placed = await api.checkout(slug, getSessionId(), {
        name: form.name.trim(),
        email: form.email.trim(),
        note: form.note.trim(),
      })
      setOrder(placed)
      setView('done')
      useCart.setState({ cart: null }) // backend cleared it; mirror locally
    } catch (err) {
      setCheckoutErr(err instanceof ApiError ? err.message : 'Checkout failed')
    } finally {
      setPlacing(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={close}
          />
          <motion.aside
            data-cart-style={variant}
            initial={variant === 'full-sheet' ? { y: '100%' } : { x: '100%' }}
            animate={variant === 'full-sheet' ? { y: 0 } : { x: 0 }}
            exit={variant === 'full-sheet' ? { y: '100%' } : { x: '100%' }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className={
              variant === 'full-sheet'
                ? 'fixed inset-0 z-50 w-full flex flex-col shadow-2xl [&>*]:w-full [&>*]:max-w-2xl [&>*]:mx-auto'
                : 'fixed top-0 right-0 z-50 h-full w-full max-w-md flex flex-col shadow-2xl'
            }
            style={{
              background: 'var(--s-bg)',
              color: 'var(--s-text)',
              ...(variant === 'slide-panel'
                ? { borderLeft: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)' }
                : {}),
            }}
          >
            <header className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)' }}>
              <h2 className="text-lg font-semibold" style={{ fontFamily: 'var(--s-display)' }}>
                {view === 'cart' ? 'Your cart' : view === 'checkout' ? 'Checkout' : 'Order placed'}
              </h2>
              <button onClick={close} aria-label="Close cart" className="text-2xl leading-none opacity-60 hover:opacity-100">×</button>
            </header>

            {/* ── Cart view ── */}
            {view === 'cart' && (
              <>
                <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
                  {items.length === 0 ? (
                    <p className="text-sm py-12 text-center" style={{ color: 'var(--s-text-muted)' }}>
                      Your cart is empty.
                    </p>
                  ) : (
                    items.map((it) => (
                      <div key={it.product_id} className="flex gap-3 items-center">
                        <div
                          className="w-14 h-14 rounded-md shrink-0 flex items-center justify-center overflow-hidden"
                          style={{ background: 'color-mix(in srgb, var(--s-primary) 16%, var(--s-bg))' }}
                        >
                          <ProductImage src={it.image_url} alt={it.name} initial={it.name} className="w-full h-full object-cover" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium truncate">{it.name}</p>
                          <p className="text-xs" style={{ color: 'var(--s-text-muted)' }}>
                            ${it.unit_price.toFixed(2)} each
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <Stepper onDec={() => setQty(it.product_id, it.qty - 1)} onInc={() => setQty(it.product_id, it.qty + 1)} qty={it.qty} busy={busy} />
                            <button onClick={() => remove(it.product_id)} className="text-xs underline" style={{ color: 'var(--s-text-subtle)' }}>
                              remove
                            </button>
                          </div>
                        </div>
                        <span className="text-sm font-semibold shrink-0">${it.line_total.toFixed(2)}</span>
                      </div>
                    ))
                  )}
                  {error && <p className="text-sm" style={{ color: 'var(--s-accent-text)' }}>{error}</p>}
                </div>
                {items.length > 0 && (
                  <footer className="px-5 py-4" style={{ borderTop: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)' }}>
                    {hasDiscount && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
                        className="mb-3 rounded-md px-3 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 flex-wrap text-center"
                        style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
                      >
                        <span aria-hidden>🛒</span>
                        <span>{cart?.discount_label ?? `Complete your order — ${Math.round(discountPct)}% off`}</span>
                        {cart?.discount_expires_at ? <PromoCountdown expiresAt={cart.discount_expires_at} /> : null}
                      </motion.div>
                    )}
                    {hasDiscount ? (
                      <>
                        <div className="flex justify-between mb-1 text-sm">
                          <span style={{ color: 'var(--s-text-muted)' }}>Subtotal</span>
                          <span className="line-through" style={{ color: 'var(--s-text-muted)' }}>${subtotal.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between mb-2 text-sm">
                          <span style={{ color: 'var(--s-text-muted)' }}>Recovery discount ({Math.round(discountPct)}%)</span>
                          <span className="font-semibold" style={{ color: 'var(--s-cta)' }}>−${discountAmt.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between mb-3">
                          <span className="font-semibold">Total</span>
                          <span className="font-semibold text-base">${total.toFixed(2)}</span>
                        </div>
                      </>
                    ) : (
                      <div className="flex justify-between mb-3">
                        <span style={{ color: 'var(--s-text-muted)' }}>Subtotal</span>
                        <span className="font-semibold">${subtotal.toFixed(2)}</span>
                      </div>
                    )}
                    <button
                      onClick={() => setView('checkout')}
                      className="w-full rounded-md py-3 text-sm font-semibold hover:opacity-90 transition-opacity"
                      style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
                    >
                      Checkout →
                    </button>
                  </footer>
                )}
              </>
            )}

            {/* ── Checkout view ── */}
            {view === 'checkout' && (
              <form onSubmit={placeOrder} className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
                <Field label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
                <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} />
                <Field label="Order note (optional)" value={form.note} onChange={(v) => setForm({ ...form, note: v })} />
                {hasDiscount && (
                  <div className="flex justify-between mt-2 text-xs">
                    <span style={{ color: 'var(--s-cta)' }}>{cart?.discount_label ?? 'Recovery discount'}</span>
                    <span style={{ color: 'var(--s-cta)' }}>−${discountAmt.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between mt-2 text-sm">
                  <span style={{ color: 'var(--s-text-muted)' }}>Total</span>
                  <span className="font-semibold">${total.toFixed(2)}</span>
                </div>
                {checkoutErr && <p className="text-sm" style={{ color: 'var(--s-accent-text)' }}>{checkoutErr}</p>}
                <button
                  type="submit"
                  disabled={placing}
                  className="w-full rounded-md py-3 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                  style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
                >
                  {placing ? 'Placing order…' : 'Place order'}
                </button>
                <button type="button" onClick={() => setView('cart')} className="text-xs underline self-center" style={{ color: 'var(--s-text-subtle)' }}>
                  ← back to cart
                </button>
              </form>
            )}

            {/* ── Confirmation view ── */}
            {view === 'done' && order && (
              <div className="flex-1 overflow-y-auto px-5 py-8 flex flex-col items-center text-center gap-3">
                <div className="text-4xl">✓</div>
                <h3 className="text-lg font-semibold" style={{ fontFamily: 'var(--s-display)' }}>Thank you, {order.customer_name.split(' ')[0]}!</h3>
                <p className="text-sm" style={{ color: 'var(--s-text-muted)' }}>
                  Your order is confirmed. Total ${order.total.toFixed(2)}.
                </p>
                <p className="text-xs font-mono mt-2 px-3 py-2 rounded-md" style={{ background: 'color-mix(in srgb, var(--s-text) 6%, var(--s-bg))' }}>
                  {order.id}
                </p>
                <p className="text-xs" style={{ color: 'var(--s-text-subtle)' }}>
                  Keep this reference to track your order with your email.
                </p>
                <button
                  onClick={() => { setView('cart'); setOpen(false); setOrder(null) }}
                  className="mt-4 rounded-md py-2.5 px-8 text-sm font-semibold hover:opacity-90 transition-opacity"
                  style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
                >
                  Keep shopping
                </button>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function Stepper({ qty, onInc, onDec, busy }: { qty: number; onInc: () => void; onDec: () => void; busy: boolean }) {
  const btn = 'w-6 h-6 rounded flex items-center justify-center text-sm disabled:opacity-40'
  const style = { border: '1px solid color-mix(in srgb, var(--s-text) 20%, transparent)' } as React.CSSProperties
  return (
    <div className="flex items-center gap-2">
      <button onClick={onDec} disabled={busy} className={btn} style={style} aria-label="Decrease">−</button>
      <span className="text-sm w-5 text-center">{qty}</span>
      <button onClick={onInc} disabled={busy} className={btn} style={style} aria-label="Increase">+</button>
    </div>
  )
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs" style={{ color: 'var(--s-text-muted)' }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md px-3 py-2.5 text-sm outline-none"
        style={{ background: 'color-mix(in srgb, var(--s-text) 5%, var(--s-bg))', color: 'var(--s-text)', border: '1px solid color-mix(in srgb, var(--s-text) 15%, transparent)' }}
      />
    </label>
  )
}
