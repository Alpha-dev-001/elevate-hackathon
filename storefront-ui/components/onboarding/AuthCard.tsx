'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { api, ApiError } from '@/lib/api'
import { useStore } from '@/lib/store'

const CATEGORIES = [
  'fashion', 'electronics', 'food', 'beauty', 'home', 'sports', 'other',
] as const

/**
 * Step 1 (auth half): email + password. Signup also collects the store
 * essentials so the slug + brand context exist before the logo drop.
 */
export function AuthCard() {
  const setMerchant = useStore((s) => s.setMerchant)
  const [mode, setMode] = useState<'signup' | 'login'>('signup')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [storeName, setStoreName] = useState('')
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('fashion')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const merchant =
        mode === 'signup'
          ? await api.signup({ email, password, store_name: storeName, category, description })
          : await api.login({ email, password })
      setMerchant(merchant)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const inputCls =
    'w-full bg-bg border border-border rounded-md px-3 py-2.5 text-text text-sm ' +
    'outline-none focus:border-accent transition-colors placeholder:text-muted'

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="card w-full max-w-md p-8"
    >
      <h1
        className="text-3xl font-bold tracking-tight mb-1"
        style={{ fontFamily: 'var(--font-display)' }}
      >
        {mode === 'signup' ? 'Create your store' : 'Welcome back'}
      </h1>
      <p className="text-muted text-sm mb-6 font-mono">
        {mode === 'signup' ? 'A logo is all it takes.' : 'Pick up where you left off.'}
      </p>

      <form onSubmit={submit} className="flex flex-col gap-3">
        {mode === 'signup' && (
          <input
            className={inputCls}
            placeholder="Store name"
            value={storeName}
            onChange={(e) => setStoreName(e.target.value)}
            required
          />
        )}
        <input
          className={inputCls}
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          className={inputCls}
          type="password"
          placeholder="Password (min 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={mode === 'signup' ? 8 : undefined}
          required
        />
        {mode === 'signup' && (
          <>
            <select
              className={inputCls}
              value={category}
              onChange={(e) => setCategory(e.target.value as (typeof CATEGORIES)[number])}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c} className="bg-bg">
                  {c[0].toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
            <input
              className={inputCls}
              placeholder="One line about the store (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </>
        )}

        {error && <p className="text-danger text-sm font-mono">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="mt-2 bg-accent text-bg font-semibold rounded-md py-2.5 text-sm
                     hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {busy ? 'One moment…' : mode === 'signup' ? 'Create store' : 'Log in'}
        </button>
      </form>

      <button
        onClick={() => {
          setMode(mode === 'signup' ? 'login' : 'signup')
          setError(null)
        }}
        className="mt-4 text-muted text-xs font-mono hover:text-accent transition-colors"
      >
        {mode === 'signup'
          ? 'Already have a store? Log in'
          : "New here? Create a store"}
      </button>
    </motion.div>
  )
}
