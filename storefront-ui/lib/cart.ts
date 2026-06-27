/**
 * Storefront cart (Zustand). The cart itself lives in Redis on the backend with
 * prices snapshotted at add-time — this store is the client mirror plus the
 * guest session id. The session id is generated once and persisted in
 * localStorage so a returning guest keeps their cart; no account required.
 */
'use client'

import { create } from 'zustand'
import { api, ApiError } from '@/lib/api'
import type { Cart } from '@/types/schemas'

const SESSION_KEY = 'elevate_session'

function getSessionId(): string {
  if (typeof window === 'undefined') return ''
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id =
      (crypto.randomUUID?.() ??
        `sess_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`)
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

interface CartState {
  slug: string | null
  cart: Cart | null
  open: boolean
  busy: boolean
  error: string | null

  init: (slug: string) => Promise<void>
  add: (productId: string, qty?: number) => Promise<boolean>
  setQty: (productId: string, qty: number) => Promise<void>
  remove: (productId: string) => Promise<void>
  clear: () => Promise<void>
  setOpen: (open: boolean) => void
  reset: () => void
}

export const useCart = create<CartState>((set, get) => ({
  slug: null,
  cart: null,
  open: false,
  busy: false,
  error: null,

  init: async (slug) => {
    set({ slug })
    const sessionId = getSessionId()
    if (!sessionId) return
    try {
      const cart = await api.getCart(slug, sessionId)
      set({ cart })
    } catch {
      // A missing/empty cart is fine — leave it null until first add.
    }
  },

  add: async (productId, qty = 1) => {
    const { slug } = get()
    if (!slug) return false
    set({ busy: true, error: null })
    try {
      const cart = await api.addToCart(slug, getSessionId(), productId, qty)
      set({ cart, open: true })
      return true
    } catch (e) {
      set({ error: e instanceof ApiError ? e.message : 'Could not add to cart' })
      return false
    } finally {
      set({ busy: false })
    }
  },

  setQty: async (productId, qty) => {
    const { slug } = get()
    if (!slug) return
    set({ busy: true, error: null })
    try {
      const cart = await api.setCartItem(slug, getSessionId(), productId, qty)
      set({ cart })
    } catch (e) {
      set({ error: e instanceof ApiError ? e.message : 'Could not update cart' })
    } finally {
      set({ busy: false })
    }
  },

  remove: async (productId) => {
    await get().setQty(productId, 0)
  },

  clear: async () => {
    const { slug } = get()
    if (!slug) return
    try {
      const cart = await api.clearCart(slug, getSessionId())
      set({ cart })
    } catch {
      /* best-effort */
    }
  },

  setOpen: (open) => set({ open }),
  reset: () => set({ cart: null, open: false, error: null }),
}))

export { getSessionId }
