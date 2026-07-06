'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useCart } from '@/lib/cart'

/**
 * Sign the merchant out: clear the httpOnly JWT cookie on the backend, drop any
 * client-side session state, then land on /login. Works even if the network call
 * fails — the point is to leave the authed session, so we always move on.
 *
 * Needed because otherwise a signed-in merchant (e.g. the demo `owoyemi`) can
 * never switch identity: /brand-review and /terminal always resolve to whoever
 * the cookie says you are, so a fresh logo upload appears to "do nothing".
 */
export default function LogoutPage() {
  const router = useRouter()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        await api.logout()
      } catch {
        // even a failed logout shouldn't trap the user — fall through to redirect
      }
      try {
        useCart.getState().reset()
      } catch {
        /* store may not be initialised — ignore */
      }
      if (cancelled) return
      // replace() so the back button can't return to an authed page
      router.replace('/login')
      // hard fallback in case client nav is swallowed
      setTimeout(() => {
        if (!cancelled && typeof window !== 'undefined' && window.location.pathname.startsWith('/logout')) {
          window.location.href = '/login'
        }
      }, 1500)
      setFailed(false)
    })()
    return () => { cancelled = true }
  }, [router])

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg text-text">
      <div className="text-center">
        <p className="text-sm font-mono text-muted">Signing you out…</p>
        {failed && (
          <a href="/login" className="text-xs underline text-muted mt-3 inline-block">Continue to sign in →</a>
        )}
      </div>
    </main>
  )
}
