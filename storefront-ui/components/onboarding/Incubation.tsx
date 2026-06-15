'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { connectTerminal } from '@/lib/ws'
import { api, ApiError } from '@/lib/api'
import { useStore } from '@/lib/store'

const PHASES = [
  'Analyzing geometry…',
  'Extracting palette…',
  'Defining brand voice…',
  'Composing guard rules…',
  'Assembling your store…',
]

/**
 * Step 2 — the incubation. Opens the terminal socket FIRST, then fires the
 * brand pipeline on open (so the brand_ready push can't race ahead of us).
 * Ambient text breathes while qwen-vl-max -> qwen-max run server-side; the
 * result arrives over the socket. A long safety net falls back to the
 * durable GET if the push is ever missed.
 */
export function Incubation({
  merchantId,
  logoUrl,
}: {
  merchantId: string
  logoUrl: string
}) {
  const setBrand = useStore((s) => s.setBrand)
  const setError = useStore((s) => s.setError)
  const [phaseIdx, setPhaseIdx] = useState(0)
  const startedRef = useRef(false)

  useEffect(() => {
    // cycle ambient text
    const ticker = setInterval(
      () => setPhaseIdx((i) => (i + 1) % PHASES.length),
      2500,
    )

    const conn = connectTerminal(merchantId, {
      onOpen: async () => {
        if (startedRef.current) return // survive a reconnect without re-firing
        startedRef.current = true
        try {
          await api.onboardingStart(logoUrl)
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Could not start brand generation')
        }
      },
      onBrandReady: (payload) => {
        if ('error' in payload) {
          setError(payload.error)
        } else {
          setBrand(payload.brand_package, payload.store_shell_url)
        }
      },
    })

    // Safety net: if no push within 2 minutes, pull the durable copy.
    const safety = setTimeout(async () => {
      try {
        const res = await api.getBrand()
        setBrand(res.brand_package, res.store_shell_url)
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) return // still cooking
        setError('Brand generation timed out. Please try again.')
      }
    }, 120_000)

    return () => {
      clearInterval(ticker)
      clearTimeout(safety)
      conn.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchantId, logoUrl])

  return (
    <div className="flex flex-col items-center justify-center text-center">
      {/* breathing orb — the store gestating */}
      <motion.div
        className="w-28 h-28 rounded-full mb-10"
        style={{ background: 'radial-gradient(circle at 30% 30%, var(--color-accent), var(--color-accent-dim))' }}
        animate={{ scale: [1, 1.12, 1], opacity: [0.8, 1, 0.8] }}
        transition={{ duration: 2.6, repeat: Infinity, ease: [0.4, 0, 0.2, 1] }}
      />

      <p className="font-mono text-xs text-accent mb-4 tracking-widest uppercase">
        Incubating
      </p>

      <div className="h-7">
        <AnimatePresence mode="wait">
          <motion.p
            key={phaseIdx}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
            className="text-text text-lg"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            {PHASES[phaseIdx]}
          </motion.p>
        </AnimatePresence>
      </div>

      <p className="text-muted text-xs mt-6 max-w-xs">
        This can take up to a minute — the brain is doing real work, not faking a
        spinner.
      </p>
    </div>
  )
}
