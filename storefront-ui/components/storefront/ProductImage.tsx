'use client'
import { useState } from 'react'

/**
 * Product image with a graceful, on-brand fallback. A dead URL (Unsplash rot,
 * a merchant's broken link) never shows the browser's broken-image glyph on the
 * storefront — it falls back to a branded tile (surface tint + the product's
 * initial in the store's display font/accent), so a missing image reads as
 * intentional, not broken. Also covers products with no image at all.
 *
 * Drop-in for a raw <img>: pass the same className/style you'd give the img and
 * both the image and the fallback fill the parent box identically.
 */
export function ProductImage({
  src,
  alt,
  className,
  style,
  initial,
}: {
  src?: string | null
  alt: string
  className?: string
  style?: React.CSSProperties
  initial?: string
}) {
  const [failed, setFailed] = useState(false)

  if (src && !failed) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={src}
        alt={alt}
        className={className}
        style={style}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    )
  }

  const ch = (initial ?? alt ?? '').trim().slice(0, 1).toUpperCase() || '·'
  return (
    <div
      className={className}
      aria-hidden
      style={{
        ...style,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'color-mix(in srgb, var(--s-primary, #808080) 12%, var(--s-bg, #111))',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--s-display, inherit)',
          color: 'var(--s-accent, #999)',
          opacity: 0.4,
          fontWeight: 800,
          fontSize: 'clamp(1.5rem, 6vw, 3rem)',
          userSelect: 'none',
        }}
      >
        {ch}
      </span>
    </div>
  )
}
