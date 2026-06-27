'use client'

import type { BrandToken } from '@/types/schemas'

interface StoreShellProps {
  /** Brand token — drives data-layout + data-spacing attributes. */
  brandToken: BrandToken
  /**
   * Pre-computed CSS custom properties from resolveTheme().
   * StoreShell intentionally does NOT recompute these — storeTheme.ts
   * is the single source of CSS variable values.
   */
  cssVars: React.CSSProperties
  children: React.ReactNode
}

/**
 * Root wrapper that applies the BrandToken CSS custom properties and
 * structural data attributes for this store's layout variant.
 *
 * Does NOT load fonts — the parent Storefront.tsx handles that so fonts
 * are loaded once regardless of layout, including during the fallback path.
 */
export function StoreShell({ brandToken, cssVars, children }: StoreShellProps) {
  return (
    <div
      style={cssVars}
      data-layout={brandToken.layout.style}
      data-spacing={brandToken.layout.spacing}
    >
      {children}
    </div>
  )
}
