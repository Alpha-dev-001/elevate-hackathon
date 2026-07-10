'use client'

import { useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { uploadProductImage, api, ApiError } from '@/lib/api'
import { groupByFingerprint } from '@/lib/fingerprint'
import type { Product } from '@/types/schemas'

/**
 * Multi-image drop zone with Vision Fingerprinting.
 *
 * Flow: drop photos → fingerprint each → group near-duplicates → upload all
 * to OSS → send only ONE per group to qwen-vl-max → update products with
 * extra image URLs from duplicates.
 *
 * This means 3 shots of the same Casablanca slides = 1 product with 3 images,
 * not 3 separate products wasting 3× the vision tokens.
 */

type Phase = 'idle' | 'fingerprinting' | 'uploading' | 'processing' | 'done' | 'error'

interface Progress {
  phase: Phase
  total: number
  deduped: number       // duplicates collapsed
  uploaded: number
  visionCount: number   // unique products sent to vision
  created: number
  uncertain: number
  failed: number
}

const MAX_CONCURRENT_UPLOADS = 5

export function ImageDropZone({
  onProductsCreated,
}: {
  onProductsCreated: (products: Product[], uncertainIds: string[]) => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState<Progress>({
    phase: 'idle', total: 0, deduped: 0, uploaded: 0, visionCount: 0,
    created: 0, uncertain: 0, failed: 0,
  })
  const [error, setError] = useState<string | null>(null)

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    setError(null)
    const imageFiles = Array.from(files).filter((f) => f.type.startsWith('image/'))
    if (!imageFiles.length) {
      setError('No image files found — drop PNG, JPG, WebP, or GIF.')
      return
    }
    if (imageFiles.length > 50) {
      setError('Max 50 images per batch — drop fewer files at a time.')
      return
    }

    // Phase 1: Fingerprint — detect near-duplicates before any network calls.
    setProgress({
      phase: 'fingerprinting', total: imageFiles.length,
      deduped: 0, uploaded: 0, visionCount: 0, created: 0, uncertain: 0, failed: 0,
    })

    const { groups } = await groupByFingerprint(imageFiles)
    const deduped = groups.reduce((n, g) => n + g.duplicates.length, 0)

    // Build a map: representative file → duplicate files' OSS URLs (filled after upload)
    const repToDupUrls = new Map<File, string[]>()
    for (const g of groups) {
      repToDupUrls.set(g.representative, [])
    }

    setProgress((p) => ({ ...p, phase: 'uploading', deduped }))

    // Phase 2: Upload ALL files to OSS (duplicates need URLs too, they just
    // don't go through vision).
    let active = 0
    let uploadErrors = 0
    // Map: file → its OSS public URL
    const fileUrlMap = new Map<File, string>()

    const uploadOne = async (file: File) => {
      while (active >= MAX_CONCURRENT_UPLOADS) {
        await new Promise((r) => setTimeout(r, 50))
      }
      active++
      try {
        const url = await uploadProductImage(file)
        fileUrlMap.set(file, url)
        setProgress((p) => ({ ...p, uploaded: p.uploaded + 1 }))
      } catch {
        uploadErrors++
      } finally {
        active--
      }
    }

    await Promise.all(imageFiles.map(uploadOne))

    // Map duplicate URLs to their representative
    for (const g of groups) {
      const dupUrls = g.duplicates
        .map((f) => fileUrlMap.get(f))
        .filter((u): u is string => !!u)
      repToDupUrls.set(g.representative, dupUrls)
    }

    // Collect representative URLs (only these go to vision)
    const repUrls: Array<{ file: File; url: string }> = []
    for (const g of groups) {
      const url = fileUrlMap.get(g.representative)
      if (url) repUrls.push({ file: g.representative, url })
    }

    if (!repUrls.length) {
      setProgress((p) => ({ ...p, phase: 'error' }))
      setError('All uploads failed — check your connection and try again.')
      return
    }

    // Phase 3: Vision batch — only representatives, not duplicates.
    setProgress((p) => ({ ...p, phase: 'processing', visionCount: repUrls.length }))

    try {
      const result = await api.visionBatch(repUrls.map((r) => r.url))
      const allProducts = result.products.map((r) => r.product)
      const uncertainIds = result.products
        .filter((r) => !r.confident)
        .map((r) => r.product.id)

      setProgress({
        phase: 'done',
        total: imageFiles.length,
        deduped,
        uploaded: imageFiles.length - uploadErrors,
        visionCount: repUrls.length,
        created: allProducts.length,
        uncertain: uncertainIds.length,
        failed: result.failed_urls.length + uploadErrors,
      })

      onProductsCreated(allProducts, uncertainIds)
    } catch (e) {
      setProgress((p) => ({ ...p, phase: 'error' }))
      setError(e instanceof ApiError ? e.message : 'Vision processing failed')
    }
  }, [onProductsCreated])

  const reset = () => {
    setProgress({
      phase: 'idle', total: 0, deduped: 0, uploaded: 0, visionCount: 0,
      created: 0, uncertain: 0, failed: 0,
    })
    setError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  return (
    <div className="w-full max-w-2xl">
      <AnimatePresence mode="wait">
        {progress.phase === 'idle' && (
          <motion.div
            key="idle"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
          >
            <div
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files)
              }}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-5 text-center transition-colors
                ${dragOver ? 'border-accent bg-accent-dim/30' : 'border-border hover:border-accent'}`}
            >
              <p className="text-sm text-text">Drop product photos</p>
              <p className="text-muted text-xs font-mono mt-1">
                Qwen identifies each product from the photo — duplicates are auto-merged
              </p>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              className="hidden"
              onChange={(e) => { if (e.target.files?.length) handleFiles(e.target.files) }}
            />
          </motion.div>
        )}

        {progress.phase === 'fingerprinting' && (
          <motion.div
            key="fingerprinting"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-5 text-center"
          >
            <div className="flex items-center justify-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <p className="text-sm text-text font-mono">
                Fingerprinting {progress.total} images…
              </p>
            </div>
            <p className="text-muted text-xs font-mono mt-1">
              Detecting duplicates to save Qwen tokens
            </p>
          </motion.div>
        )}

        {progress.phase === 'uploading' && (
          <motion.div
            key="uploading"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-5 text-center"
          >
            <div className="flex items-center justify-center gap-2 mb-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <p className="text-sm text-text font-mono">
                Uploading {progress.uploaded}/{progress.total}
              </p>
            </div>
            {progress.deduped > 0 && (
              <p className="text-xs font-mono mt-1" style={{ color: 'var(--color-accent)' }}>
                {progress.deduped} duplicate{progress.deduped !== 1 ? 's' : ''} detected — saving {progress.deduped} vision call{progress.deduped !== 1 ? 's' : ''}
              </p>
            )}
            <div className="w-full bg-surface-2 rounded-full h-1.5 mt-2">
              <motion.div
                className="bg-accent h-1.5 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${(progress.uploaded / progress.total) * 100}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </motion.div>
        )}

        {progress.phase === 'processing' && (
          <motion.div
            key="processing"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-5 text-center"
          >
            <div className="flex items-center justify-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <p className="text-sm text-text">
                Qwen is cataloguing {progress.visionCount} unique product{progress.visionCount !== 1 ? 's' : ''}…
              </p>
            </div>
            <p className="text-muted text-xs font-mono mt-1">
              Identifying products, writing descriptions, suggesting prices
            </p>
          </motion.div>
        )}

        {progress.phase === 'done' && (
          <motion.div
            key="done"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-4 text-center"
          >
            <p className="text-sm text-text">
              Created <span className="text-accent font-semibold">{progress.created}</span> product{progress.created !== 1 ? 's' : ''}
              {progress.deduped > 0 && (
                <span className="text-muted"> from {progress.total} photos ({progress.deduped} duplicate{progress.deduped !== 1 ? 's' : ''} merged)</span>
              )}
              {progress.uncertain > 0 && (
                <span className="text-muted"> · {progress.uncertain} need{progress.uncertain === 1 ? 's' : ''} your review</span>
              )}
            </p>
            {progress.failed > 0 && (
              <p className="text-xs text-muted font-mono mt-1">
                {progress.failed} image{progress.failed !== 1 ? 's' : ''} couldn&apos;t be processed
              </p>
            )}
            <button
              onClick={reset}
              className="mt-3 text-xs font-mono text-muted hover:text-accent transition-colors"
            >
              Add more photos
            </button>
          </motion.div>
        )}

        {progress.phase === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-4 text-center"
          >
            <p className="text-danger text-sm">{error || 'Something went wrong'}</p>
            <button
              onClick={reset}
              className="mt-3 text-xs font-mono text-muted hover:text-accent transition-colors"
            >
              Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
