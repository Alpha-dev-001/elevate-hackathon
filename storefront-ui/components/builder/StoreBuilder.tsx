'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { PublicStore, BrandGuardRules } from '@/types/schemas'
import { api, ApiError } from '@/lib/api'
import { useBuilderStore } from '@/lib/builderStore'
import { BuilderLeftPanel } from './BuilderLeftPanel'
import { BuilderPreview } from './BuilderPreview'

/**
 * The Store Builder split-screen. Left: controls (layout, sections, colors,
 * advisory). Right: live preview via DSLRenderer. The merchant's drag-to-reorder
 * is the human-in-the-loop checkpoint over Qwen's recommendation.
 */
export function StoreBuilder({ slug }: { slug: string }) {
  const router = useRouter()
  const [store, setStore] = useState<PublicStore | null>(null)
  const [guards, setGuards] = useState<BrandGuardRules | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [published, setPublished] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setFromStore = useBuilderStore((s) => s.setFromStore)
  const markPublished = useBuilderStore((s) => s.markPublished)

  useEffect(() => {
    let cancelled = false
    // RBAC gate: the builder is merchant-only, and only for the merchant who
    // owns THIS store. Customers / wrong merchants are bounced to sign in.
    api.me()
      .then((m) => {
        if (cancelled) return
        if (m.slug !== slug) { router.replace('/terminal'); return }
        return Promise.all([api.getStore(slug), api.getBrandGuards()]).then(([s, g]) => {
          if (cancelled) return
          setStore(s)
          setGuards(g)
          if (s.brand_token?.layout_dsl) setFromStore(s.brand_token.layout_dsl, s.brand_token)
        })
      })
      .catch((e) => {
        if (cancelled) return
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) router.replace('/login')
        else setError('Could not load your store.')
      })
    return () => { cancelled = true }
  }, [slug, setFromStore, router])

  const onPublish = async () => {
    const dsl = useBuilderStore.getState().draftDSL
    if (!dsl) return
    setPublishing(true)
    try {
      await api.saveDsl(slug, dsl)            // optimistic: persist the draft
      try { await api.publish() } catch { /* already live — fine */ }
      markPublished()
      setPublishing(false)
      setPublished(true)                      // ask before leaving the builder
    } catch {
      setError('Publish failed — your changes are still saved locally. Try again.')
      setPublishing(false)
    }
  }

  const onRegenerate = async () => {
    try {
      const dsl = await api.regenerateDsl(slug)
      const token = useBuilderStore.getState().draftToken
      if (token) setFromStore(dsl, { ...token, layout_dsl: dsl })
    } catch { setError('Regeneration failed. Try again.') }
  }

  if (error) {
    return <main className="min-h-screen flex items-center justify-center"><p className="text-danger font-mono text-sm">{error}</p></main>
  }
  if (!store) {
    return <main className="min-h-screen flex items-center justify-center"><p className="text-muted font-mono text-sm">Opening the builder…</p></main>
  }

  return (
    <main className="h-screen flex" style={{ background: 'var(--color-bg, #0A0A0B)', color: '#fff' }}>
      <BuilderLeftPanel guards={guards} onPublish={onPublish} onRegenerate={onRegenerate} publishing={publishing} />
      <BuilderPreview store={store} />

      {published && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
             onClick={() => setPublished(false)}>
          <div className="rounded-2xl p-6 max-w-sm w-full mx-4 text-center"
               style={{ background: 'var(--color-surface, #111113)', border: '1px solid var(--color-border, #2A2A30)' }}
               onClick={(e) => e.stopPropagation()}>
            <p className="text-lg font-semibold mb-1">Your store is live ✨</p>
            <p className="text-sm mb-5" style={{ color: 'var(--color-text-muted, #9AA0A8)' }}>
              Do you want to view your store now?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setPublished(false)}
                className="flex-1 py-2.5 rounded-full text-sm font-medium"
                style={{ border: '1px solid var(--color-border, #2A2A30)', color: '#fff' }}
              >
                Keep editing
              </button>
              <button
                onClick={() => router.push(`/s/${slug}`)}
                className="flex-1 py-2.5 rounded-full text-sm font-semibold"
                style={{ background: 'var(--color-accent, #6EE7B7)', color: '#0A0A0B' }}
              >
                View store →
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
