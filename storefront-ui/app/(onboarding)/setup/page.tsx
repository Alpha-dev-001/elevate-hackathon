'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { useStore } from '@/lib/store'
import { AuthCard } from '@/components/onboarding/AuthCard'
import { LogoUpload } from '@/components/onboarding/LogoUpload'
import { Incubation } from '@/components/onboarding/Incubation'

/**
 * The onboarding spine: auth -> logo -> incubation -> (route to) brand review.
 * One page, driven by auth + the onboarding phase in the store.
 */
export default function SetupPage() {
  const router = useRouter()
  const { merchant, authChecked, phase, error } = useStore()
  const setMerchant = useStore((s) => s.setMerchant)
  const setAuthChecked = useStore((s) => s.setAuthChecked)
  const setPhase = useStore((s) => s.setPhase)
  const resetOnboarding = useStore((s) => s.resetOnboarding)
  const [logoUrl, setLogoUrl] = useState('')

  // Resolve the session cookie once on mount.
  useEffect(() => {
    if (authChecked) return
    api
      .me()
      .then(setMerchant)
      .catch((e) => {
        if (!(e instanceof ApiError) || e.status !== 401) {
          // 401 just means "not logged in"; anything else is worth surfacing.
          console.error('auth check failed', e)
        }
      })
      .finally(() => setAuthChecked(true))
  }, [authChecked, setMerchant, setAuthChecked])

  // A live merchant must not re-onboard — a new logo would regenerate and
  // overwrite their brand/logo/layout. Send them to their terminal instead.
  // (The backend also hard-blocks /onboarding/start for a live store.)
  useEffect(() => {
    if (merchant?.is_live) router.replace('/terminal')
  }, [merchant, router])

  // Once the brand is ready, glide to the review.
  useEffect(() => {
    if (phase === 'ready') router.push('/brand-review')
  }, [phase, router])

  if (!authChecked) {
    return <Centered><p className="text-muted font-mono text-sm">Loading…</p></Centered>
  }

  if (!merchant) {
    return <Centered><AuthCard /></Centered>
  }

  if (phase === 'failed') {
    return (
      <Centered>
        <div className="card max-w-md p-8 text-center">
          <p className="text-danger font-mono text-sm mb-4">{error}</p>
          <button
            onClick={resetOnboarding}
            className="bg-accent text-bg font-semibold rounded-md py-2.5 px-6 text-sm hover:opacity-90"
          >
            Try again
          </button>
        </div>
      </Centered>
    )
  }

  if (phase === 'generating') {
    return <Centered><Incubation merchantId={merchant.id} logoUrl={logoUrl} /></Centered>
  }

  // phase 'idle' — logged in, awaiting the logo
  return (
    <Centered>
      <LogoUpload
        onSubmit={(url) => {
          setLogoUrl(url)
          setPhase('generating')
        }}
      />
    </Centered>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen flex items-center justify-center p-6">{children}</main>
  )
}
