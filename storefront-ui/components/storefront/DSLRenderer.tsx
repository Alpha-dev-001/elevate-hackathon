'use client'
import { useMemo } from 'react'
import type { PublicStore, LayoutDSL } from '@/types/schemas'
import { LayoutDSLSchema } from '@/types/schemas'
import '@/lib/registerVariants'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { DSLSection } from './DSLSection'
import { DSLNav } from './DSLNav'
import { DSLFooter } from './DSLFooter'
import { FallbackStorefront } from './FallbackStorefront'

export function DSLRenderer({
  store, slug, preview, onOpenProduct, dslOverride,
}: {
  store: PublicStore
  slug: string
  preview?: boolean
  onOpenProduct?: (id: string) => void
  /** Builder injects a draft DSL without mutating the store. */
  dslOverride?: LayoutDSL | null
}) {
  const parsed = useMemo(() => {
    const candidate = dslOverride ?? store.brand_token?.layout_dsl
    if (!candidate) return null
    const r = LayoutDSLSchema.safeParse(candidate)
    return r.success ? r.data : null
  }, [store.brand_token, dslOverride])

  if (!parsed || !store.brand_token) {
    return <FallbackStorefront store={store} slug={slug} />
  }

  const theme = resolveTheme(store)
  const hasAnnounce = parsed.sections[0]?.variant === 'announcement-bar'

  return (
    <StoreShell brandToken={store.brand_token} cssVars={theme.cssVars}>
      <div data-store={slug}>
        {!hasAnnounce && <DSLNav store={store} navStyle={parsed.global_config.nav_style} />}
        {parsed.sections.map((section, i) => (
          <DSLSection
            key={`${section.type}-${i}`}
            section={section}
            store={store}
            slug={slug}
            globalConfig={parsed.global_config}
            preview={preview}
            onOpenProduct={onOpenProduct}
          />
        ))}
        <DSLFooter store={store} />
      </div>
    </StoreShell>
  )
}
