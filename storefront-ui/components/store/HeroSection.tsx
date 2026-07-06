'use client'

import { motion, useReducedMotion } from 'framer-motion'
import type { BrandToken } from '@/types/schemas'
import { BrandLogo } from '@/components/storefront/BrandLogo'

interface HeroSectionProps {
  brandToken: BrandToken
  storeName: string
  tagline: string
  /** SVG string — the store's logo mark. May be empty. */
  logoMark: string
  /** Merchant's real uploaded logo; falls back to logoMark when empty. */
  logoUrl?: string
}

/**
 * Four hero layout variants, driven by brandToken.layout.hero_type:
 *   full-bleed   — centered, full-width gradient header (editorial)
 *   text-forward — left-aligned typographic punch (bold-grid)
 *   split        — text left / logo right (dual emphasis)
 *   texture-bg   — radial gradient, logo centered, warm feel (warm-craft)
 */
export function HeroSection({ brandToken, storeName, tagline, logoMark, logoUrl }: HeroSectionProps) {
  const prefersReduced = useReducedMotion()
  const { layout, colors, typography } = brandToken
  const fade = {
    initial: { opacity: 0, y: prefersReduced ? 0 : 20 },
    animate: { opacity: 1, y: 0 },
  }
  const displayStyle: React.CSSProperties = {
    fontFamily: 'var(--s-display)',
    letterSpacing: 'var(--s-letter-spacing)',
  }

  if (layout.hero_type === 'full-bleed') {
    return (
      <motion.header
        {...fade}
        transition={{ duration: prefersReduced ? 0 : 0.6, ease: [0.4, 0, 0.2, 1] }}
        className="relative w-full flex flex-col items-center justify-center text-center py-24 px-6 overflow-hidden"
        style={{
          background: `linear-gradient(160deg, ${colors.primary}22 0%, ${colors.background} 60%)`,
        }}
      >
        <BrandLogo
          logoUrl={logoUrl}
          logoMark={logoMark}
          storeName={storeName}
          className="w-20 h-20 mb-6"
        />
        <h1
          className="text-5xl md:text-7xl font-bold tracking-tight mb-4 [text-wrap:balance] max-w-3xl"
          style={displayStyle}
        >
          {storeName}
        </h1>
        <p className="text-lg max-w-md" style={{ color: colors.text_muted }}>
          {tagline}
        </p>
      </motion.header>
    )
  }

  if (layout.hero_type === 'text-forward') {
    return (
      <motion.header
        {...fade}
        transition={{ duration: prefersReduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="pt-16 pb-10 px-6 max-w-5xl mx-auto"
      >
        <p
          className="text-xs font-mono uppercase tracking-[0.25em] mb-4"
          style={{ color: colors.accent }}
        >
          {brandToken.mood.replaceAll('-', ' ')}
        </p>
        <h1
          className="text-6xl md:text-8xl font-black leading-none mb-5 uppercase [text-wrap:balance]"
          style={displayStyle}
        >
          {storeName}
        </h1>
        <p className="text-base max-w-lg" style={{ color: colors.text_muted }}>
          {tagline}
        </p>
      </motion.header>
    )
  }

  if (layout.hero_type === 'split') {
    return (
      <motion.header
        {...fade}
        transition={{ duration: prefersReduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="flex flex-col md:flex-row items-center gap-8 py-20 px-6 max-w-5xl mx-auto"
      >
        <div className="flex-1">
          <h1
            className="text-4xl md:text-6xl font-bold mb-4 [text-wrap:balance]"
            style={displayStyle}
          >
            {storeName}
          </h1>
          <p className="text-lg leading-relaxed" style={{ color: colors.text_muted }}>
            {tagline}
          </p>
        </div>
        {logoMark && (
          <div
            className="w-32 h-32 shrink-0 [&>svg]:w-full [&>svg]:h-full"
            role="img"
            aria-label={`${storeName} logo`}
            dangerouslySetInnerHTML={{ __html: logoMark }}
          />
        )}
      </motion.header>
    )
  }

  // texture-bg — full-width radial gradient, logo centered
  return (
    <motion.header
      {...fade}
      transition={{ duration: prefersReduced ? 0 : 0.55, ease: [0.4, 0, 0.2, 1] }}
      className="relative w-full text-center py-24 px-6 overflow-hidden"
      style={{
        background: `radial-gradient(ellipse 80% 60% at 50% 0%, ${colors.primary}40 0%, ${colors.background} 70%)`,
      }}
    >
      {logoMark && (
        <div
          className="w-20 h-20 mx-auto mb-6 [&>svg]:w-full [&>svg]:h-full"
          role="img"
          aria-label={`${storeName} logo`}
          dangerouslySetInnerHTML={{ __html: logoMark }}
        />
      )}
      <h1
        className="text-4xl md:text-6xl font-bold mb-3 [text-wrap:balance] max-w-2xl mx-auto"
        style={displayStyle}
      >
        {storeName}
      </h1>
      <p className="text-base" style={{ color: colors.accent }}>
        {tagline}
      </p>
    </motion.header>
  )
}
