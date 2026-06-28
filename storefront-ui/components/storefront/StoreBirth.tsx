'use client'
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

type StepEvent = { step: string; label: string; index: number; total: number }

/**
 * Full-screen brand-generation animation driven by the StoreBirth SSE stream.
 * Each step appears as the real Qwen work completes — no fake delays. On
 * `complete`, hands the brand_token + layout_dsl up to onComplete.
 *
 * eventSourceFactory is injectable for tests (jsdom has no EventSource).
 */
export function StoreBirth({
  slug, onComplete, apiBase = '', eventSourceFactory,
}: {
  slug: string
  onComplete: (payload: { brand_token: unknown; layout_dsl: unknown }) => void
  apiBase?: string
  eventSourceFactory?: (url: string) => EventSource
}) {
  const [current, setCurrent] = useState<StepEvent | null>(null)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const url = `${apiBase}/api/brand/birth/${slug}`
    const make = eventSourceFactory ?? ((u: string) => new EventSource(u))
    const es = make(url)

    es.addEventListener('step', (e: MessageEvent) => {
      const data = JSON.parse(e.data) as StepEvent
      setCurrent(data)
      setProgress(data.total ? (data.index + 1) / data.total : 0)
    })
    es.addEventListener('complete', (e: MessageEvent) => {
      es.close()
      onComplete(JSON.parse(e.data))
    })
    es.addEventListener('error', () => {
      setError('Brand generation hit a snag. Retrying shortly…')
    })

    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  return (
    <main className="fixed inset-0 flex flex-col items-center justify-center px-6"
          style={{ background: '#0A0A0B', color: '#fff' }}>
      <div className="w-full max-w-md">
        <div className="h-0.5 w-full rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.1)' }}>
          <motion.div className="h-full" style={{ background: '#6EE7B7' }}
                      animate={{ width: `${Math.round(progress * 100)}%` }}
                      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }} />
        </div>
        <div className="mt-8 h-8 text-center">
          <AnimatePresence mode="wait">
            <motion.p key={current?.step ?? 'idle'}
                      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.15 }}
                      className="text-sm font-mono" style={{ color: error ? '#FF6B6B' : 'rgba(255,255,255,0.8)' }}>
              {error ?? current?.label ?? 'Waking up the brand engine…'}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </main>
  )
}
