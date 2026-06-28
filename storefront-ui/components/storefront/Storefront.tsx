'use client'

import { useEffect, useState } from 'react'
import { api, ApiError } from '@/lib/api'
import type { PublicStore } from '@/types/schemas'
import { useCart } from '@/lib/cart'
import { DSLRenderer } from './DSLRenderer'

/**
 * The live customer-facing store. Handles three responsibilities then
 * delegates all layout rendering to LayoutRouter:
 *
 *   1. Fetch the store payload from the backend
 *   2. Load the brand's Google Fonts (preferred from brand_token if present)
 *   3. Initialise the guest cart for this slug
 *   4. Show loading / error / not-found states
 *   5. Render <LayoutRouter> which picks the right layout variant
 *
 * Layout decisions, CSS vars, filter state, and cart UI all live in LayoutRouter.
 */
export function Storefront({ slug, initialProductId }: { slug: string; initialProductId?: string | null }) {
  const [store, setStore] = useState<PublicStore | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'notfound' | 'error'>('loading')

  const initCart = useCart((s) => s.init)

  useEffect(() => {
    api
      .getStore(slug)
      .then((s) => {
        setStore(s)
        setStatus('ok')
      })
      .catch((e) => setStatus(e instanceof ApiError && e.status === 404 ? 'notfound' : 'error'))
  }, [slug])

  // Initialise the guest cart for this store
  useEffect(() => {
    initCart(slug)
  }, [slug, initCart])

  // Load the brand's Google Fonts. Prefer brand_token fonts when present —
  // they may differ from the legacy typography object.
  useEffect(() => {
    if (!store) return
    const bt = store.brand_token
    const fonts = bt
      ? [bt.typography.display_font, bt.typography.body_font]
      : [store.typography.display_font, store.typography.body_font]
    const fams = fonts
      .filter(Boolean)
      .map((f) => `family=${f.trim().replace(/\s+/g, '+')}:wght@300;400;500;600;700`)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `https://fonts.googleapis.com/css2?${fams.join('&')}&display=swap`
    document.head.appendChild(link)
    return () => {
      document.head.removeChild(link)
    }
  }, [store])

  if (status === 'loading') {
    return <Center><p className="text-muted font-mono text-sm">Opening the store…</p></Center>
  }
  if (status === 'notfound') {
    return <Center><p className="text-muted font-mono text-sm">This store isn't live yet.</p></Center>
  }
  if (status === 'error' || !store) {
    return <Center><p className="text-danger font-mono text-sm">Couldn't load this store.</p></Center>
  }

  return <DSLRenderer store={store} slug={slug} initialProductId={initialProductId} />
}

function Center({ children }: { children: React.ReactNode }) {
  return <main className="min-h-screen flex items-center justify-center bg-bg">{children}</main>
}
