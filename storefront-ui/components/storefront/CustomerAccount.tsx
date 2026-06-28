'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { PublicStore } from '@/types/schemas'
import { api, ApiError } from '@/lib/api'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { useCustomer } from '@/lib/customerAuth'

type Mode = 'login' | 'register'

/**
 * Per-brand customer sign-in / register. Fully themed by the store's brand DNA
 * (StoreShell + resolved CSS vars) — a customer of this store never sees the
 * Elevate chrome, only the store's. RBAC: this is the customer surface.
 */
export function CustomerAccount({ slug }: { slug: string }) {
  const router = useRouter()
  const [store, setStore] = useState<PublicStore | null>(null)
  const [mode, setMode] = useState<Mode>('login')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const { customer, init, login, register, logout } = useCustomer()

  useEffect(() => { api.getStore(slug).then(setStore).catch(() => {}) }, [slug])
  useEffect(() => { init(slug) }, [slug, init])

  // Load the brand fonts for this store.
  useEffect(() => {
    if (!store) return
    const bt = store.brand_token
    const fonts = bt ? [bt.typography.display_font, bt.typography.body_font] : [store.typography.display_font, store.typography.body_font]
    const fams = fonts.filter(Boolean).map((f) => `family=${f.trim().replace(/\s+/g, '+')}:wght@300;400;500;600;700`)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `https://fonts.googleapis.com/css2?${fams.join('&')}&display=swap`
    document.head.appendChild(link)
    return () => { document.head.removeChild(link) }
  }, [store])

  const theme = useMemo(() => (store ? resolveTheme(store) : null), [store])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      if (mode === 'register') await register(slug, form.name.trim(), form.email.trim(), form.password)
      else await login(slug, form.email.trim(), form.password)
      router.push(`/s/${slug}`)
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  if (!store || !theme) {
    return <main className="min-h-screen flex items-center justify-center bg-bg"><p className="text-muted font-mono text-sm">Loading…</p></main>
  }

  const inner = (
    <main className="min-h-screen flex items-center justify-center px-5 py-16"
          style={{ background: 'var(--s-bg)', color: 'var(--s-text)' }}>
      <div className="w-full max-w-sm flex flex-col gap-6">
        <header className="flex flex-col items-center gap-2 text-center">
          <a href={`/s/${slug}`} className="w-12 h-12 [&>svg]:w-full [&>svg]:h-full" aria-label={`${store.store_name} home`}
             dangerouslySetInnerHTML={{ __html: store.icons.logo_mark }} />
          <h1 className="text-2xl font-bold" style={{ fontFamily: 'var(--s-display)' }}>{store.store_name}</h1>
          <p className="text-sm" style={{ color: 'var(--s-text-muted)' }}>
            {customer ? `Signed in as ${customer.name}` : mode === 'login' ? 'Welcome back' : 'Create your account'}
          </p>
        </header>

        {customer ? (
          <div className="flex flex-col gap-3">
            <a href={`/s/${slug}`} className="w-full text-center py-3 rounded-full font-medium"
               style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}>Continue shopping →</a>
            <button onClick={() => logout()} className="text-sm underline self-center" style={{ color: 'var(--s-text-muted)' }}>Sign out</button>
          </div>
        ) : (
          <>
            <div className="flex rounded-full p-1" style={{ background: 'var(--s-surface)' }}>
              {(['login', 'register'] as Mode[]).map((m) => (
                <button key={m} onClick={() => { setMode(m); setErr(null) }}
                        className="flex-1 py-2 rounded-full text-sm font-medium transition-colors capitalize"
                        style={mode === m ? { background: 'var(--s-accent)', color: 'var(--s-bg)' } : { color: 'var(--s-text-muted)' }}>
                  {m === 'login' ? 'Sign in' : 'Register'}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="flex flex-col gap-3">
              {mode === 'register' && (
                <AccountField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} autoComplete="name" />
              )}
              <AccountField label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} autoComplete="email" />
              <AccountField label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })}
                            autoComplete={mode === 'register' ? 'new-password' : 'current-password'} />
              {err && <p className="text-sm" style={{ color: 'var(--s-danger, #FF6B6B)' }}>{err}</p>}
              <button type="submit" disabled={busy}
                      className="w-full py-3 rounded-full font-medium disabled:opacity-50 transition-opacity"
                      style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}>
                {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
              </button>
            </form>
          </>
        )}

        <a href={`/s/${slug}`} className="text-xs text-center underline" style={{ color: 'var(--s-text-subtle, var(--s-text-muted))' }}>
          ← Back to {store.store_name}
        </a>
      </div>
    </main>
  )

  // Wrap in StoreShell when the brand token exists so CSS vars + corner radius apply.
  return store.brand_token ? <StoreShell brandToken={store.brand_token} cssVars={theme.cssVars}>{inner}</StoreShell> : <div style={theme.cssVars}>{inner}</div>
}

function AccountField({
  label, value, onChange, type = 'text', autoComplete,
}: { label: string; value: string; onChange: (v: string) => void; type?: string; autoComplete?: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs" style={{ color: 'var(--s-text-muted)' }}>{label}</span>
      <input type={type} value={value} autoComplete={autoComplete} required
             onChange={(e) => onChange(e.target.value)}
             className="rounded-lg px-3 py-2.5 text-sm outline-none"
             style={{ background: 'color-mix(in srgb, var(--s-text) 5%, var(--s-bg))', color: 'var(--s-text)', border: '1px solid color-mix(in srgb, var(--s-text) 15%, transparent)' }} />
    </label>
  )
}
