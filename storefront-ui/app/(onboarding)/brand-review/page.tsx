'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import { useStore } from '@/lib/store'
import { BrandPreview } from '@/components/onboarding/BrandPreview'

/**
 * Step 3 — review the generated brand and publish. Reads the package from the
 * store; on a hard refresh it rehydrates from the durable GET so the page
 * stands on its own.
 */
export default function BrandReviewPage() {
  const router = useRouter()
  const { brand, storeShellUrl, liveUrl } = useStore()
  const setBrand = useStore((s) => s.setBrand)
  const setLiveUrl = useStore((s) => s.setLiveUrl)
  const [loading, setLoading] = useState(!brand)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Rehydrate on direct load / refresh.
  useEffect(() => {
    if (brand) return
    api
      .getBrand()
      .then((res) => setBrand(res.brand_package, res.store_shell_url))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) {
          router.replace('/setup') // not generated yet
        } else {
          setError('Could not load your brand.')
        }
      })
      .finally(() => setLoading(false))
  }, [brand, setBrand, router])

  const publish = async () => {
    setPublishing(true)
    setError(null)
    try {
      const res = await api.publish()
      setLiveUrl(res.storefront_url)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Publish failed')
    } finally {
      setPublishing(false)
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-muted font-mono text-sm">Loading your brand…</p>
      </main>
    )
  }

  if (!brand) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-danger font-mono text-sm">{error ?? 'No brand found.'}</p>
      </main>
    )
  }

  return (
    <main className="min-h-screen flex flex-col items-center p-6 py-16 gap-8">
      <BrandPreview pkg={brand} />

      {liveUrl ? (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="card max-w-2xl w-full p-6 text-center border-accent"
        >
          <p className="font-mono text-xs text-accent uppercase tracking-widest mb-2">
            Live
          </p>
          <p className="text-text mb-3">Your store is live.</p>
          <a
            href={liveUrl}
            className="text-accent font-mono text-sm underline underline-offset-4 break-all"
          >
            {storeShellUrl ?? liveUrl}
          </a>
        </motion.div>
      ) : (
        <div className="max-w-2xl w-full flex flex-col items-center gap-3">
          {error && <p className="text-danger text-sm font-mono">{error}</p>}
          <button
            onClick={publish}
            disabled={publishing}
            className="bg-accent text-bg font-semibold rounded-md py-3 px-10 text-sm
                       hover:opacity-90 disabled:opacity-50 transition-opacity accent-glow"
          >
            {publishing ? 'Publishing…' : 'Publish store →'}
          </button>
          <p className="text-muted text-xs font-mono">
            Products come next — you can publish now and add them after.
          </p>
        </div>
      )}
    </main>
  )
}
