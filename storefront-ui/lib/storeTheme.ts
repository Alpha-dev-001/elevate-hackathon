/**
 * Shared storefront theming — single source of CSS custom property values.
 *
 * resolveTheme()  ← new: BrandToken-aware, returns full layout config + CSS vars
 * storeThemeVars() ← legacy: palette-only CSS vars (used by ProductDetail)
 * useStoreFonts()  ← legacy: Google Fonts loader (used by ProductDetail)
 */
'use client'

import { useEffect } from 'react'
import type { PublicStore, BrandToken } from '@/types/schemas'
import { readableOn } from '@/lib/color'

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Blend fg toward bg by weight. 0 = full bg, 1 = full fg. Returns hex. */
export function blendHex(fg: string, bg: string, weight: number): string {
  const parse = (h: string): [number, number, number] | null => {
    const hex = h.replace('#', '').trim()
    if (hex.length !== 6) return null
    const n = parseInt(hex, 16)
    return isNaN(n) ? null : [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const fRgb = parse(fg)
  const bRgb = parse(bg)
  if (!fRgb || !bRgb) return fg
  const ch = (a: number, b: number) =>
    Math.max(0, Math.min(255, Math.round(a * weight + b * (1 - weight))))
      .toString(16)
      .padStart(2, '0')
  return `#${ch(fRgb[0], bRgb[0])}${ch(fRgb[1], bRgb[1])}${ch(fRgb[2], bRgb[2])}`
}

// ─── Legacy helpers (used by ProductDetail) ───────────────────────────────────

export function storeThemeVars(store: PublicStore): React.CSSProperties {
  const { palette, typography } = store
  const accentText = readableOn(palette.accent, palette.background)
  const textMuted = readableOn(blendHex(palette.text, palette.background, 0.6), palette.background)
  const textSubtle = readableOn(blendHex(palette.text, palette.background, 0.42), palette.background)
  return {
    '--s-bg': palette.background,
    '--s-text': palette.text,
    '--s-text-muted': textMuted,
    '--s-text-subtle': textSubtle,
    '--s-accent': palette.accent,
    '--s-accent-text': accentText,
    '--s-primary': palette.primary,
    '--s-secondary': palette.secondary,
    '--s-surface': blendHex(palette.background, palette.text, 0.05),
    '--s-radius': '8px',
    '--s-display': `'${typography.display_font}', sans-serif`,
    background: palette.background,
    color: palette.text,
    fontFamily: `'${typography.body_font}', sans-serif`,
    minHeight: '100vh',
  } as React.CSSProperties
}

/** Load the brand's Google Fonts for the lifetime of the page. */
export function useStoreFonts(store: PublicStore | null) {
  useEffect(() => {
    if (!store) return
    const fams = [store.typography.display_font, store.typography.body_font]
      .filter(Boolean)
      .map((f) => `family=${f.trim().replace(/\s+/g, '+')}:wght@400;500;600;700`)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `https://fonts.googleapis.com/css2?${fams.join('&')}&display=swap`
    document.head.appendChild(link)
    return () => {
      document.head.removeChild(link)
    }
  }, [store])
}

// ─── BrandToken-aware theme ───────────────────────────────────────────────────

export interface ResolvedTheme {
  /** CSS custom properties to apply via style= on the root element. */
  cssVars: React.CSSProperties
  layoutStyle: 'editorial' | 'bold-grid' | 'minimal-dark' | 'warm-craft' | null
  gridVariant: '2col-featured' | '3col-equal' | 'masonry'
  cardStyle: 'borderless' | 'outlined' | 'elevated' | 'colored-bg'
  categoryStyle: 'pill' | 'underline-tab' | 'minimal-text'
  brandToken: BrandToken | null
}

/**
 * Single source of truth for --s-* CSS custom properties.
 * Prefers brand_token when present; falls back to palette + typography.
 * NEVER throws on null brand_token.
 */
export function resolveTheme(store: PublicStore): ResolvedTheme {
  const bt = store.brand_token ?? null

  if (bt) {
    const letterSpacing =
      bt.typography.letter_spacing === 'tight'
        ? '-0.02em'
        : bt.typography.letter_spacing === 'wide'
        ? '0.08em'
        : '0em'
    const spacing =
      bt.layout.spacing === 'compact'
        ? '1rem'
        : bt.layout.spacing === 'generous'
        ? '2.5rem'
        : '1.5rem'

    const cssVars = {
      '--s-primary': bt.colors.primary,
      '--s-accent': bt.colors.accent,
      '--s-accent-text': readableOn(bt.colors.accent, bt.colors.background),
      '--s-bg': bt.colors.background,
      '--s-surface': bt.colors.surface,
      '--s-text': bt.colors.text,
      '--s-text-muted': bt.colors.text_muted,
      '--s-text-subtle': readableOn(
        blendHex(bt.colors.text, bt.colors.background, 0.4),
        bt.colors.background,
      ),
      '--s-display': `'${bt.typography.display_font}', serif`,
      '--s-radius': bt.layout.border_radius,
      '--s-spacing': spacing,
      '--s-letter-spacing': letterSpacing,
      background: bt.colors.background,
      color: bt.colors.text,
      fontFamily: `'${bt.typography.body_font}', sans-serif`,
      minHeight: '100vh',
    } as React.CSSProperties

    return {
      cssVars,
      layoutStyle: bt.layout.style,
      gridVariant: bt.layout.product_grid,
      cardStyle: bt.layout.card_style,
      categoryStyle: bt.layout.category_style,
      brandToken: bt,
    }
  }

  // Fallback: derive from legacy palette + typography
  const accentText = readableOn(store.palette.accent, store.palette.background)
  const textMuted = readableOn(
    blendHex(store.palette.text, store.palette.background, 0.6),
    store.palette.background,
  )
  const textSubtle = readableOn(
    blendHex(store.palette.text, store.palette.background, 0.42),
    store.palette.background,
  )

  const cssVars = {
    '--s-primary': store.palette.primary,
    '--s-accent': store.palette.accent,
    '--s-accent-text': accentText,
    '--s-bg': store.palette.background,
    '--s-surface': blendHex(store.palette.background, store.palette.text, 0.05),
    '--s-text': store.palette.text,
    '--s-text-muted': textMuted,
    '--s-text-subtle': textSubtle,
    '--s-display': `'${store.typography.display_font}', sans-serif`,
    '--s-radius': '8px',
    '--s-spacing': '1.5rem',
    '--s-letter-spacing': '0em',
    background: store.palette.background,
    color: store.palette.text,
    fontFamily: `'${store.typography.body_font}', sans-serif`,
    minHeight: '100vh',
  } as React.CSSProperties

  return {
    cssVars,
    layoutStyle: null,
    gridVariant: '3col-equal',
    cardStyle: 'elevated',
    categoryStyle: 'pill',
    brandToken: null,
  }
}
