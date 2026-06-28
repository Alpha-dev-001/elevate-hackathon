'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, ApiError } from '@/lib/api'

/** Merchant sign-in (RBAC: merchant role). Customers use /s/{slug}/account. */
export default function MerchantLoginPage() {
  const router = useRouter()
  const [form, setForm] = useState({ email: '', password: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      const m = await api.login({ email: form.email.trim(), password: form.password })
      // Live store → dashboard; mid-onboarding → resume setup.
      router.push(m.is_live ? '/terminal' : '/setup')
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-5 py-16 bg-bg text-text">
      <div className="w-full max-w-sm flex flex-col gap-6">
        <header className="text-center">
          <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: 'var(--font-display)' }}>Elevate</h1>
          <p className="text-muted text-sm mt-1">Merchant sign in</p>
        </header>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} autoComplete="email" />
          <Field label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} autoComplete="current-password" />
          {err && <p className="text-sm text-danger">{err}</p>}
          <button type="submit" disabled={busy}
                  className="w-full py-3 rounded-lg bg-accent text-bg font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="text-xs text-center text-muted">
          New here? <Link href="/setup" className="underline">Build your store →</Link>
        </p>
      </div>
    </main>
  )
}

function Field({ label, value, onChange, type = 'text', autoComplete }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; autoComplete?: string
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <input type={type} value={value} autoComplete={autoComplete} required
             onChange={(e) => onChange(e.target.value)}
             className="rounded-lg px-3 py-2.5 text-sm outline-none bg-surface text-text border border-border" />
    </label>
  )
}
