'use client'

import { useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { uploadProductImage, api, ApiError } from '@/lib/api'
import { groupByFingerprint } from '@/lib/fingerprint'
import { parseProductCsv } from '@/lib/csv'
import type { Product } from '@/types/schemas'

/**
 * One smart drop zone for product inventory — CSV or photos, detected from
 * what's actually dropped, instead of two separate boxes on the page.
 *
 * CSV rows go through the existing batched-description pipeline
 * (api.addProductsBatch). Photos go through Vision Fingerprinting: fingerprint
 * each → group near-duplicates → upload all to OSS → send only ONE per group
 * to qwen-vl-max → update products with extra image URLs from duplicates.
 * A drop can contain both at once — CSV rows import first (fast), then
 * photos run through vision.
 *
 * This means 3 shots of the same Casablanca slides = 1 product with 3 images,
 * not 3 separate products wasting 3× the vision tokens.
 */

type Phase = 'idle' | 'importing' | 'fingerprinting' | 'uploading' | 'processing' | 'done' | 'error'

interface Progress {
  phase: Phase
  total: number
  deduped: number       // duplicates collapsed
  uploaded: number
  visionCount: number   // unique products sent to vision
  visionDone: number    // how many of visionCount have come back so far
  created: number
  uncertain: number
  failed: number
  csvAdded: number
  csvSkipped: number
}

const MAX_CONCURRENT_UPLOADS = 5
// Matches the backend's VISION_CONCURRENCY — one round trip per chunk this
// size means the progress counter advances roughly every "round" of Qwen
// calls instead of sitting frozen for the whole batch.
const VISION_CHUNK_SIZE = 5

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}

// A plain FileList from dataTransfer.files never recurses into a dropped
// folder — the browser only lists the folder itself, not what's inside it.
// Reading a folder's contents requires the separate FileSystemEntry API
// (webkitGetAsEntry), walked recursively, since directoryReader.readEntries
// caps how many entries it returns per call and must be re-invoked until empty.
type FileSystemEntryLike = {
  isFile: boolean
  isDirectory: boolean
  file: (success: (f: File) => void, error: () => void) => void
  createReader: () => { readEntries: (success: (e: FileSystemEntryLike[]) => void, error: () => void) => void }
}

function readAllDirEntries(reader: ReturnType<FileSystemEntryLike['createReader']>): Promise<FileSystemEntryLike[]> {
  return new Promise((resolve) => {
    const all: FileSystemEntryLike[] = []
    const readBatch = () => {
      reader.readEntries((batch) => {
        if (!batch.length) { resolve(all); return }
        all.push(...batch)
        readBatch()
      }, () => resolve(all))
    }
    readBatch()
  })
}

async function filesFromEntry(entry: FileSystemEntryLike): Promise<File[]> {
  if (entry.isFile) {
    return new Promise((resolve) => entry.file((f) => resolve([f]), () => resolve([])))
  }
  if (entry.isDirectory) {
    const entries = await readAllDirEntries(entry.createReader())
    const nested = await Promise.all(entries.map(filesFromEntry))
    return nested.flat()
  }
  return []
}

async function filesFromDataTransfer(dataTransfer: DataTransfer): Promise<File[]> {
  const items = dataTransfer.items
  if (items && items.length) {
    const entries = Array.from(items)
      .map((item) => item.webkitGetAsEntry?.() as FileSystemEntryLike | null)
      .filter((e): e is FileSystemEntryLike => !!e)
    if (entries.length) {
      const nested = await Promise.all(entries.map(filesFromEntry))
      return nested.flat()
    }
  }
  return Array.from(dataTransfer.files)
}

const EMPTY_PROGRESS: Progress = {
  phase: 'idle', total: 0, deduped: 0, uploaded: 0, visionCount: 0, visionDone: 0,
  created: 0, uncertain: 0, failed: 0, csvAdded: 0, csvSkipped: 0,
}

export function ImageDropZone({
  onProductsCreated,
  onCsvProductsAdded,
  onBusyChange,
}: {
  onProductsCreated: (products: Product[], uncertainIds: string[]) => void
  onCsvProductsAdded: (products: Product[]) => void
  onBusyChange?: (busy: boolean) => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState<Progress>(EMPTY_PROGRESS)
  const [error, setError] = useState<string | null>(null)

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    setError(null)
    const all = Array.from(files)
    const csvFile = all.find((f) => f.name.toLowerCase().endsWith('.csv') || f.type === 'text/csv')
    const imageFiles = all.filter((f) => f.type.startsWith('image/'))

    if (!csvFile && !imageFiles.length) {
      setError('Drop a CSV or product photos — no other file types supported.')
      return
    }
    if (imageFiles.length > 50) {
      setError('Max 50 images per batch — drop fewer files at a time.')
      return
    }

    // Signal "still working" up to the parent page for the whole operation —
    // not just the local component's lifetime, so it survives as long as this
    // page instance does even if the merchant loses track of which phase
    // they're in. Cleared in every exit path below (done/error/return).
    onBusyChange?.(true)

    let csvAdded = 0
    let csvSkipped = 0

    // CSV import first — fast (one batched request), never blocked on vision.
    if (csvFile) {
      setProgress({ ...EMPTY_PROGRESS, phase: 'importing' })
      try {
        const text = await csvFile.text()
        const { rows, skipped } = parseProductCsv(text)
        csvSkipped = skipped
        if (rows.length) {
          const created = await api.addProductsBatch(rows)
          csvAdded = created.length
          onCsvProductsAdded(created)
        } else if (!imageFiles.length) {
          // CSV was the only thing dropped and had nothing usable in it.
          setProgress((p) => ({ ...p, phase: 'error' }))
          setError('No valid rows found in the CSV. Columns: name, price, stock, image_url, category.')
          onBusyChange?.(false)
          return
        }
      } catch (e) {
        setProgress((p) => ({ ...p, phase: 'error' }))
        setError(e instanceof ApiError ? e.message : 'CSV import failed')
        onBusyChange?.(false)
        return
      }
    }

    if (!imageFiles.length) {
      setProgress({ ...EMPTY_PROGRESS, phase: 'done', csvAdded, csvSkipped })
      onBusyChange?.(false)
      return
    }

    // Phase 1: Fingerprint — detect near-duplicates before any network calls.
    setProgress({ ...EMPTY_PROGRESS, phase: 'fingerprinting', total: imageFiles.length, csvAdded, csvSkipped })

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
      onBusyChange?.(false)
      return
    }

    // Phase 3: Vision batch, chunked — one visionBatch call per chunk instead
    // of a single request for the whole set. A 15-photo drop used to sit on
    // one static "Qwen is cataloguing…" message for its entire ~30-90s
    // duration with no sense of progress; chunking surfaces a live count as
    // each round comes back, so it's clear Qwen is actually still working.
    setProgress((p) => ({ ...p, phase: 'processing', visionCount: repUrls.length, visionDone: 0 }))

    let createdCount = 0
    let uncertainCount = 0
    let failedCount = 0

    try {
      for (const batch of chunk(repUrls, VISION_CHUNK_SIZE)) {
        const result = await api.visionBatch(batch.map((r) => r.url))
        const batchProducts = result.products.map((r) => r.product)
        const batchUncertain = result.products.filter((r) => !r.confident).map((r) => r.product.id)
        createdCount += batchProducts.length
        uncertainCount += batchUncertain.length
        failedCount += result.failed_urls.length
        // Hand off each chunk as it lands — pending-product cards appear
        // incrementally, so the merchant sees Qwen actively producing
        // results instead of one big reveal at the very end.
        if (batchProducts.length) onProductsCreated(batchProducts, batchUncertain)
        setProgress((p) => ({ ...p, visionDone: p.visionDone + batch.length }))
      }

      setProgress({
        phase: 'done',
        total: imageFiles.length,
        deduped,
        uploaded: imageFiles.length - uploadErrors,
        visionCount: repUrls.length,
        visionDone: repUrls.length,
        created: createdCount,
        uncertain: uncertainCount,
        failed: failedCount + uploadErrors,
        csvAdded,
        csvSkipped,
      })
    } catch (e) {
      // Whatever finished before the failing chunk already went out via
      // per-chunk onProductsCreated calls above — nothing to lose here.
      setProgress((p) => ({ ...p, phase: 'error' }))
      setError(e instanceof ApiError ? e.message : 'Vision processing failed')
    } finally {
      onBusyChange?.(false)
    }
  }, [onProductsCreated, onCsvProductsAdded, onBusyChange])

  const reset = () => {
    setProgress(EMPTY_PROGRESS)
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
                const dataTransfer = e.dataTransfer
                filesFromDataTransfer(dataTransfer).then((files) => {
                  if (files.length) handleFiles(files)
                })
              }}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-5 text-center transition-colors
                ${dragOver ? 'border-accent bg-accent-dim/30' : 'border-border hover:border-accent'}`}
            >
              <p className="text-sm text-text">Drop a CSV or product photos</p>
              <p className="text-muted text-xs font-mono mt-1">
                columns: name, price, stock, image_url, category — or photos: Qwen identifies each product, duplicates are auto-merged
              </p>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,.csv,text/csv"
              multiple
              className="hidden"
              onChange={(e) => { if (e.target.files?.length) handleFiles(e.target.files) }}
            />
          </motion.div>
        )}

        {progress.phase === 'importing' && (
          <motion.div
            key="importing"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="card p-5 text-center"
          >
            <div className="flex items-center justify-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <p className="text-sm text-text font-mono">Importing CSV…</p>
            </div>
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
              <p className="text-sm text-text font-mono">
                Qwen is cataloguing {progress.visionDone}/{progress.visionCount}…
              </p>
            </div>
            <div className="w-full bg-surface-2 rounded-full h-1.5 mt-2">
              <motion.div
                className="bg-accent h-1.5 rounded-full"
                animate={{ width: `${(progress.visionDone / Math.max(1, progress.visionCount)) * 100}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <p className="text-muted text-xs font-mono mt-2">
              Identifying products, writing descriptions, suggesting prices — this can take
              a minute or more for larger batches. Stay on this page until it finishes.
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
            {progress.csvAdded > 0 && (
              <p className="text-sm text-text">
                Added <span className="text-accent font-semibold">{progress.csvAdded}</span> product{progress.csvAdded !== 1 ? 's' : ''} from CSV
                {progress.csvSkipped > 0 && <span className="text-muted"> ({progress.csvSkipped} invalid row{progress.csvSkipped !== 1 ? 's' : ''} skipped)</span>}
              </p>
            )}
            {progress.visionCount > 0 && (
              <p className="text-sm text-text">
                Created <span className="text-accent font-semibold">{progress.created}</span> product{progress.created !== 1 ? 's' : ''}
                {progress.deduped > 0 && (
                  <span className="text-muted"> from {progress.total} photos ({progress.deduped} duplicate{progress.deduped !== 1 ? 's' : ''} merged)</span>
                )}
                {progress.uncertain > 0 && (
                  <span className="text-muted"> · {progress.uncertain} need{progress.uncertain === 1 ? 's' : ''} your review</span>
                )}
              </p>
            )}
            {progress.failed > 0 && (
              <p className="text-xs text-muted font-mono mt-1">
                {progress.failed} image{progress.failed !== 1 ? 's' : ''} couldn&apos;t be processed
              </p>
            )}
            <button
              onClick={reset}
              className="mt-3 text-xs font-mono text-muted hover:text-accent transition-colors"
            >
              Add more
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
