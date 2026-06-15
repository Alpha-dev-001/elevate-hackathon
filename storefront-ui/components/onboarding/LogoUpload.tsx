'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'

/**
 * Step 1 (logo half). The real flow uploads the logo straight to OSS via an
 * STS token and hands the backend the resulting URL. OSS credentials aren't
 * wired yet, so for now this takes a pasted image URL — same contract from the
 * backend's view (it only ever sees a URL string). Swaps to drag-and-drop the
 * moment the STS endpoint is live.
 */
export function LogoUpload({ onSubmit }: { onSubmit: (logoUrl: string) => void }) {
  const [url, setUrl] = useState('')
  const [touched, setTouched] = useState(false)

  const looksValid = /^https?:\/\/.+/i.test(url.trim())

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="card w-full max-w-xl p-10 text-center"
    >
      <p className="font-mono text-xs text-accent mb-3 tracking-widest uppercase">
        The drop
      </p>
      <h2
        className="text-3xl font-bold tracking-tight mb-2"
        style={{ fontFamily: 'var(--font-display)' }}
      >
        Drop your logo
      </h2>
      <p className="text-muted text-sm mb-8">
        Qwen reads it, then builds your entire brand — colors, voice, and the
        rules that protect it.
      </p>

      {url.trim() && looksValid && (
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mb-6 flex justify-center"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url.trim()}
            alt="logo preview"
            className="max-h-32 rounded-lg border border-border object-contain bg-surface-2 p-2"
            onError={() => setTouched(true)}
          />
        </motion.div>
      )}

      <input
        className="w-full bg-bg border border-border rounded-md px-3 py-3 text-text text-sm
                   outline-none focus:border-accent transition-colors placeholder:text-muted text-center"
        placeholder="Paste a logo image URL  (https://…)"
        value={url}
        onChange={(e) => {
          setUrl(e.target.value)
          setTouched(true)
        }}
      />

      {touched && url.trim() && !looksValid && (
        <p className="text-warning text-xs font-mono mt-2">
          That doesn’t look like an image URL.
        </p>
      )}

      <button
        disabled={!looksValid}
        onClick={() => onSubmit(url.trim())}
        className="mt-6 w-full bg-accent text-bg font-semibold rounded-md py-3 text-sm
                   hover:opacity-90 disabled:opacity-40 transition-opacity"
      >
        Generate my brand →
      </button>

      <p className="text-muted text-[11px] font-mono mt-4">
        Dev mode: paste-a-URL stands in for OSS upload until credentials are wired.
      </p>
    </motion.div>
  )
}
