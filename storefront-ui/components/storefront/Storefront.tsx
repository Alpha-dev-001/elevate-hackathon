'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import type { PublicStore } from '@/types/schemas'
import { ProductGrid } from './ProductGrid'

/**
 * The live customer-facing store. Themed entirely by the merchant's generated
 * brand — palette becomes CSS vars, the two brand fonts load from Google Fonts,
 * the logo mark renders inline. Nothing here uses the Elevate admin theme.
 */
export function Storefront({ slug }: { slug: string }) {
  const [store, setStore] = useState<PublicStore | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'notfound' | 'error'>('loading')

  useEffect(() => {
    api
      .getStore(slug)
      .then((s) => {
        setStore(s)
        setStatus('ok')
      })
      .catch((e) => setStatus(e instanceof ApiError && e.status === 404 ? 'notfound' : 'error'))
  }, [slug])

  // Load the brand's Google Fonts for this store.
  useEffect(() => {
    if (!store) return
    const fams = [store.typography.display_font, store.typography.body_font]
      .filter(Boolean)
      .map((f) => `family=${f.trim().replace(/\s+/g, '+')}:wght@400;500;600;700`)
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
    return <Center><p className="text-muted font-mono text-sm">This store isn’t live yet.</p></Center>
  }
  if (status === 'error' || !store) {
    return <Center><p className="text-danger font-mono text-sm">Couldn’t load this store.</p></Center>
  }

  const { palette, typography } = store
  const themeVars = {
    '--s-bg': palette.background,
    '--s-text': palette.text,
    '--s-accent': palette.accent,
    '--s-primary': palette.primary,
    '--s-secondary': palette.secondary,
    '--s-display': `'${typography.display_font}', sans-serif`,
    background: palette.background,
    color: palette.text,
    fontFamily: `'${typography.body_font}', sans-serif`,
    minHeight: '100vh',
  } as React.CSSProperties

  const hasPromo = store.promos.length > 0

  return (
    <main style={themeVars}>
      {hasPromo && (
        <div
          className="w-full text-center py-2.5 text-sm font-medium"
          style={{ background: palette.accent, color: palette.background }}
        >
          {store.promos[0].label}
        </div>
      )}

      <div className="max-w-5xl mx-auto px-5 py-12">
        <motion.header
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
          className="flex flex-col items-center text-center gap-3 mb-12"
        >
          <div
            className="w-16 h-16 [&>svg]:w-full [&>svg]:h-full"
            dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }}
          />
          <h1
            className="text-4xl sm:text-5xl font-bold tracking-tight"
            style={{ fontFamily: 'var(--s-display)' }}
          >
            {store.store_name}
          </h1>
          <p className="text-base" style={{ color: palette.accent }}>
            {store.tagline}
          </p>
        </motion.header>

        <ProductGrid products={store.products} logoMark={store.icons.logo_mark} />

        <footer className="text-center mt-16 text-xs font-mono" style={{ opacity: 0.4 }}>
          Powered by Elevate
        </footer>
      </div>
    </main>
  )
}

function Center({ children }: { children: React.ReactNode }) {
  return <main className="min-h-screen flex items-center justify-center bg-bg">{children}</main>
}
