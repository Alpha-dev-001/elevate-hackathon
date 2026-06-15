'use client'

import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { uploadLogo, ApiError } from '@/lib/api'

/**
 * Step 1 (logo half). Real direct-to-OSS upload: the file goes straight to OSS
 * via a presigned PUT, and we hand the resulting public URL upward — qwen-vl
 * fetches it from there. A "paste a URL" escape hatch stays for resilience
 * (that path uses the backend's base64 fallback).
 */
export function LogoUpload({ onSubmit }: { onSubmit: (logoUrl: string) => void }) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [mode, setMode] = useState<'file' | 'url'>('file')
  const [url, setUrl] = useState('')
  const urlValid = /^https?:\/\/.+/i.test(url.trim())

  const takeFile = (f: File | undefined) => {
    setError(null)
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setError('That’s not an image — use PNG, JPG, WebP, or SVG.')
      return
    }
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }

  const generate = async () => {
    setError(null)
    if (mode === 'url') {
      if (urlValid) onSubmit(url.trim())
      return
    }
    if (!file) return
    setBusy(true)
    try {
      const publicUrl = await uploadLogo(file)
      onSubmit(publicUrl)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Upload failed')
      setBusy(false)
    }
  }

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

      {mode === 'file' ? (
        <>
          <div
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              takeFile(e.dataTransfer.files?.[0])
            }}
            className={`cursor-pointer rounded-lg border-2 border-dashed p-8 transition-colors
              ${dragOver ? 'border-accent bg-accent-dim/30' : 'border-border hover:border-accent'}`}
          >
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="logo preview"
                className="max-h-32 mx-auto rounded-lg object-contain bg-surface-2 p-2"
              />
            ) : (
              <div className="py-6">
                <p className="text-text text-sm mb-1">Drag your logo here</p>
                <p className="text-muted text-xs font-mono">or click to choose a file</p>
              </div>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
            className="hidden"
            onChange={(e) => takeFile(e.target.files?.[0])}
          />
          {file && (
            <p className="text-muted text-xs font-mono mt-2 truncate">{file.name}</p>
          )}
        </>
      ) : (
        <input
          className="w-full bg-bg border border-border rounded-md px-3 py-3 text-text text-sm
                     outline-none focus:border-accent transition-colors placeholder:text-muted text-center"
          placeholder="Paste a logo image URL  (https://…)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      )}

      {error && <p className="text-danger text-xs font-mono mt-3">{error}</p>}

      <button
        disabled={busy || (mode === 'file' ? !file : !urlValid)}
        onClick={generate}
        className="mt-6 w-full bg-accent text-bg font-semibold rounded-md py-3 text-sm
                   hover:opacity-90 disabled:opacity-40 transition-opacity"
      >
        {busy ? 'Uploading…' : 'Generate my brand →'}
      </button>

      <button
        onClick={() => {
          setMode(mode === 'file' ? 'url' : 'file')
          setError(null)
        }}
        className="mt-4 text-muted text-[11px] font-mono hover:text-accent transition-colors"
      >
        {mode === 'file' ? 'or paste an image URL instead' : '← upload a file instead'}
      </button>
    </motion.div>
  )
}
