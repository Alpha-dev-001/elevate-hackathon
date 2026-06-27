'use client'

import { useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import Link from 'next/link'
import type { PublicProduct, BrandToken } from '@/types/schemas'
import { useCart } from '@/lib/cart'

/**
 * A single product tile. Colors come from CSS vars set by the Storefront
 * wrapper (--s-bg / --s-text / --s-text-muted / --s-text-subtle / --s-accent /
 * --s-primary) so every store is themed by its own generated brand.
 *
 * cardStyle drives the visual treatment of the card container:
 *   borderless   — no border, muted bottom separator, generous padding
 *   outlined     — thin border at 20% text opacity, uses --s-radius
 *   elevated     — box-shadow, surface background, rounded (default)
 *   colored-bg   — primary at 8% opacity background, accent price
 *
 * featured (optional) — renders the card in a larger "hero" format,
 * used for the first product in a 2col-featured grid.
 */
export function ProductCard({
  product,
  index = 0,
  logoMark,
  slug,
  cardStyle = 'elevated',
  featured = false,
  brandToken,
}: {
  product: PublicProduct
  index?: number
  logoMark?: string
  slug?: string
  cardStyle?: 'borderless' | 'outlined' | 'elevated' | 'colored-bg'
  featured?: boolean
  brandToken?: BrandToken | null
}) {
  const prefersReduced = useReducedMotion()
  const [imgFailed, setImgFailed] = useState(false)
  const add = useCart((s) => s.add)
  const busy = useCart((s) => s.busy)

  const showImage = product.image_url && !imgFailed
  const discounted = product.compare_at_price != null
  const href = `/s/${slug}/${product.id}`
  const radius = brandToken?.layout.border_radius ?? '8px'

  // ── Card container style per variant ──────────────────────────────────────
  const containerStyle = ((): React.CSSProperties => {
    switch (cardStyle) {
      case 'borderless':
        return {
          borderBottom: `1px solid color-mix(in srgb, var(--s-text) 10%, transparent)`,
          paddingBottom: featured ? '2rem' : '1rem',
        }
      case 'outlined':
        return {
          border: `1px solid color-mix(in srgb, var(--s-text-muted) 33%, transparent)`,
          borderRadius: radius,
          overflow: 'hidden',
        }
      case 'colored-bg':
        return {
          background: brandToken
            ? `${brandToken.colors.primary}14`
            : 'color-mix(in srgb, var(--s-primary) 8%, transparent)',
          borderRadius: radius,
          overflow: 'hidden',
        }
      case 'elevated':
      default:
        return {
          border: '1px solid color-mix(in srgb, var(--s-text) 12%, transparent)',
          background: 'color-mix(in srgb, var(--s-text) 3%, var(--s-bg))',
          borderRadius: radius,
          overflow: 'hidden',
          boxShadow: featured ? '0 4px 24px rgba(0,0,0,0.18)' : '0 2px 8px rgba(0,0,0,0.1)',
        }
    }
  })()

  const imageBg: React.CSSProperties =
    cardStyle === 'colored-bg'
      ? { background: 'color-mix(in srgb, var(--s-primary) 12%, var(--s-bg))' }
      : { background: 'color-mix(in srgb, var(--s-primary) 16%, var(--s-bg))' }

  return (
    <motion.div
      initial={{ opacity: 0, y: prefersReduced ? 0 : 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay: prefersReduced ? 0 : Math.min(index * 0.05, 0.4),
        duration: prefersReduced ? 0 : 0.5,
        ease: [0.4, 0, 0.2, 1],
      }}
      className="flex flex-col group"
      style={containerStyle}
    >
      {/* Image well */}
      <Link href={href} className="block" aria-label={product.name}>
        <div
          className={`w-full flex items-center justify-center relative overflow-hidden ${
            featured ? 'aspect-[16/9] md:aspect-[21/9]' : 'aspect-square'
          }`}
          style={imageBg}
        >
          {product.promo_label && (
            <span
              className="absolute top-2 left-2 text-[10px] font-semibold px-2 py-0.5 rounded-full z-10"
              style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}
            >
              {product.promo_label}
            </span>
          )}
          {showImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={product.image_url!}
              alt={product.name}
              className="w-full h-full object-contain"
              loading={featured ? 'eager' : 'lazy'}
              onError={() => setImgFailed(true)}
            />
          ) : logoMark ? (
            <div
              className="w-10 h-10 [&>svg]:w-full [&>svg]:h-full"
              aria-hidden="true"
              dangerouslySetInnerHTML={{ __html: logoMark }}
              style={{ opacity: 0.18 }}
            />
          ) : (
            <span
              className="text-4xl font-bold select-none"
              aria-hidden="true"
              style={{ fontFamily: 'var(--s-display)', color: 'var(--s-accent)', opacity: 0.5 }}
            >
              {product.name.slice(0, 1).toUpperCase()}
            </span>
          )}

          {!product.available && (
            <span
              className="absolute top-2 right-2 text-[10px] font-mono px-2 py-0.5 rounded-full"
              style={{ background: 'var(--s-bg)', color: 'var(--s-text)', opacity: 0.85 }}
            >
              Sold out
            </span>
          )}
        </div>
      </Link>

      <div
        className={`flex flex-col gap-1.5 flex-1 ${
          cardStyle === 'borderless' ? 'pt-3 pb-2' : 'p-4'
        }`}
      >
        <div className="flex justify-between items-start gap-2">
          <Link href={href}>
            <h3
              className={`font-semibold leading-tight hover:underline underline-offset-4 ${
                featured ? 'text-xl md:text-2xl' : ''
              }`}
              style={{ fontFamily: 'var(--s-display)' }}
            >
              {product.name}
            </h3>
          </Link>
          <div className="shrink-0 text-right">
            <span
              className={`font-semibold ${featured ? 'text-lg' : ''}`}
              style={{
                color:
                  cardStyle === 'colored-bg' && brandToken
                    ? brandToken.colors.accent
                    : 'var(--s-accent-text)',
              }}
            >
              ${product.price.toFixed(2)}
            </span>
            {discounted && (
              <span className="block text-xs line-through" style={{ color: 'var(--s-text-subtle)' }}>
                ${product.compare_at_price!.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {product.category && (
          <span
            className="text-[11px] font-mono uppercase tracking-wide"
            style={{ color: 'var(--s-text-subtle)' }}
          >
            {product.category}
          </span>
        )}

        {product.description && (
          <p
            className={`text-sm leading-relaxed mt-0.5 ${featured ? 'line-clamp-4' : 'line-clamp-3'}`}
            style={{ color: 'var(--s-text-muted)' }}
          >
            {product.description}
          </p>
        )}

        <button
          type="button"
          disabled={!product.available || busy}
          onClick={() => add(product.id)}
          className="mt-3 w-full py-2 text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: 'var(--s-accent)',
            color: 'var(--s-bg)',
            borderRadius: radius,
          }}
        >
          {product.available ? 'Add to cart' : 'Sold out'}
        </button>
      </div>
    </motion.div>
  )
}
