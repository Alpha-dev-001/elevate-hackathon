/**
 * Vision Fingerprinting — perceptual image hashing for dedup.
 *
 * Before uploading photos to the vision pipeline, compute a fingerprint for
 * each image. Near-duplicates (same product shot from a slightly different
 * angle, different lighting, resized copies) collapse into one group. Only
 * one representative per group goes through qwen-vl-max — saving tokens and
 * preventing "Casablanca Slides × 3" in the catalog.
 *
 * Uses average hash (aHash): resize to 8×8, grayscale, threshold at the mean.
 * Produces a 16-char hex string. Two images with hamming distance ≤ 5 are
 * considered near-duplicates.
 *
 * Why aHash over pHash: it's simpler, faster (no DCT), and sufficient for
 * detecting the common case — same product photographed multiple times.
 * pHash handles geometric transforms better but adds complexity for marginal
 * gain in a product-photo context.
 */

const HASH_SIZE = 8 // 8×8 = 64 bits = 16 hex chars

/**
 * Compute a perceptual hash of an image file. Returns a 16-char hex string.
 * Uses an off-screen canvas to avoid any DOM side effects.
 */
export function computeFingerprint(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = HASH_SIZE
        canvas.height = HASH_SIZE
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) {
          reject(new Error('Canvas 2D context unavailable'))
          return
        }
        ctx.drawImage(img, 0, 0, HASH_SIZE, HASH_SIZE)
        const { data } = ctx.getImageData(0, 0, HASH_SIZE, HASH_SIZE)

        // Grayscale + average
        const grays: number[] = []
        let sum = 0
        for (let i = 0; i < data.length; i += 4) {
          const g = Math.round(data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114)
          grays.push(g)
          sum += g
        }
        const avg = sum / grays.length

        // Build 64-bit hash: 1 if pixel >= average, 0 otherwise
        let hash = ''
        for (let i = 0; i < grays.length; i += 4) {
          let nibble = 0
          for (let bit = 0; bit < 4 && i + bit < grays.length; bit++) {
            if (grays[i + bit] >= avg) nibble |= (1 << (3 - bit))
          }
          hash += nibble.toString(16)
        }
        resolve(hash)
      } finally {
        URL.revokeObjectURL(url)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error(`Could not load image for fingerprinting: ${file.name}`))
    }
    img.src = url
  })
}

/**
 * Hamming distance between two hex hash strings. Counts the number of bits
 * that differ. Lower = more similar. ≤ 5 is the near-duplicate threshold for
 * 64-bit hashes.
 */
export function hammingDistance(a: string, b: string): number {
  if (a.length !== b.length) return Infinity
  let dist = 0
  for (let i = 0; i < a.length; i++) {
    const x = parseInt(a[i], 16) ^ parseInt(b[i], 16)
    // Count set bits in the nibble
    dist += ((x >> 3) & 1) + ((x >> 2) & 1) + ((x >> 1) & 1) + (x & 1)
  }
  return dist
}

const DUPLICATE_THRESHOLD = 5

export interface FingerprintGroup {
  /** The first file in the group — this one goes through vision. */
  representative: File
  /** Near-duplicates of the representative (same product, different shot). */
  duplicates: File[]
  /** The perceptual hash of the representative. */
  hash: string
}

/**
 * Group files by perceptual similarity. Each group's representative is the
 * file that will be uploaded + sent to vision. Duplicates are uploaded to
 * OSS but NOT sent to vision — they become additional image_urls on the
 * resulting product.
 */
export async function groupByFingerprint(files: File[]): Promise<{
  groups: FingerprintGroup[]
  failed: File[]
}> {
  const hashes: Array<{ file: File; hash: string | null }> = await Promise.all(
    files.map(async (file) => {
      try {
        return { file, hash: await computeFingerprint(file) }
      } catch {
        return { file, hash: null }
      }
    }),
  )

  const groups: FingerprintGroup[] = []
  const failed: File[] = []
  const assigned = new Set<number>()

  for (let i = 0; i < hashes.length; i++) {
    if (assigned.has(i)) continue
    const h = hashes[i]

    if (h.hash === null) {
      // Can't fingerprint — treat as its own group (still process it)
      groups.push({ representative: h.file, duplicates: [], hash: '' })
      assigned.add(i)
      continue
    }

    const group: FingerprintGroup = {
      representative: h.file,
      duplicates: [],
      hash: h.hash,
    }
    assigned.add(i)

    for (let j = i + 1; j < hashes.length; j++) {
      if (assigned.has(j)) continue
      const other = hashes[j]
      if (other.hash === null) continue
      if (hammingDistance(h.hash, other.hash) <= DUPLICATE_THRESHOLD) {
        group.duplicates.push(other.file)
        assigned.add(j)
      }
    }

    groups.push(group)
  }

  return { groups, failed }
}
