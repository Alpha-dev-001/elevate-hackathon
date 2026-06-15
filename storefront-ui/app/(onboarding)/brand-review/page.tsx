'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { useStore } from '@/lib/store'
import { BrandPreview } from '@/components/onboarding/BrandPreview'

/**
 * Step 3 — review the generated brand, then continue to add products. Reads the
 * package from the store; on a hard refresh it rehydrates from the durable GET
 * so the page stands on its own.
 */
export default function BrandReviewPage() {
  const router = useRouter()
  const { brand } = useStore()
  const setBrand = useStore((s) => s.setBrand)
  const [loading, setLoading] = useState(!brand)
  const [error, setError] = useState<string | null>(null)

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
      <div className="max-w-2xl w-full flex flex-col items-center gap-2">
        <button
          onClick={() => router.push('/products')}
          className="bg-accent text-bg font-semibold rounded-md py-3 px-10 text-sm
                     hover:opacity-90 transition-opacity accent-glow"
        >
          Add products →
        </button>
        <p className="text-muted text-xs font-mono">This is your brand. Next, stock the shelves.</p>
      </div>
    </main>
  )
}
