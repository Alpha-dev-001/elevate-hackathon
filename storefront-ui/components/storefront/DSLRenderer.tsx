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
import { Cart } from './Cart'
import { useCart } from '@/lib/cart'

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
  const openCart = useCart((s) => s.setOpen)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)

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
  // Promo bar is redundant when an announcement-bar section already leads.
  const showPromoBar = store.promos.length > 0 && !hasAnnounce

  return (
    <StoreShell brandToken={store.brand_token} cssVars={theme.cssVars}>
      {showPromoBar && (
        <div className="w-full text-center py-2.5 text-sm font-medium"
             style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}>
          {store.promos[0].label}
        </div>
      )}
      {!preview && (
        <>
          <button
            onClick={() => openCart(true)}
            aria-label={`Open cart (${cartCount} items)`}
            className="fixed top-4 right-4 z-30 rounded-full w-12 h-12 flex items-center justify-center shadow-lg hover:opacity-90 transition-opacity"
            style={{ background: 'var(--s-accent)', color: 'var(--s-bg)' }}
          >
            <span aria-hidden className="text-lg">🛒</span>
            {cartCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full text-[11px] font-bold flex items-center justify-center"
                    style={{ background: 'var(--s-bg)', color: 'var(--s-text)', border: '1px solid var(--s-accent)' }}>
                {cartCount}
              </span>
            )}
          </button>
          <Cart />
        </>
      )}
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
