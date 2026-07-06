'use client'

import { useState } from 'react'

/**
 * The store's brand mark. Prefers the merchant's *actual* uploaded logo
 * (logoUrl) and falls back to Qwen's generated SVG mark (logoMark) when there's
 * no upload — or when the image fails to load (broken URL, OSS hiccup). This is
 * why a merchant sees the logo they uploaded, not an AI approximation of it.
 *
 * The caller owns sizing via `className` (e.g. "w-20 h-20 mb-6"); the image is
 * always `object-contain` so an arbitrary aspect ratio letterboxes cleanly
 * inside that box and is never stretched. `decorative` mirrors each call site's
 * original a11y intent — true where a wordmark sits right beside the mark (so we
 * don't announce the store name twice).
 */
export function BrandLogo({
  logoUrl,
  logoMark,
  storeName,
  className = '',
  decorative = false,
}: {
  logoUrl?: string
  logoMark: string
  storeName: string
  className?: string
  decorative?: boolean
}) {
  const [imgFailed, setImgFailed] = useState(false)
  const hasImage = !!logoUrl && logoUrl.trim() !== '' && !imgFailed

  if (hasImage) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- external OSS URL, arbitrary host
      <img
        src={logoUrl}
        alt={decorative ? '' : `${storeName} logo`}
        aria-hidden={decorative || undefined}
        onError={() => setImgFailed(true)}
        className={`block object-contain ${className}`}
      />
    )
  }

  if (!logoMark) return null

  return (
    <div
      className={`[&>svg]:w-full [&>svg]:h-full ${className}`}
      role={decorative ? undefined : 'img'}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : `${storeName} logo`}
      dangerouslySetInnerHTML={{ __html: logoMark }}
    />
  )
}
