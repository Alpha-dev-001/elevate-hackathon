'use client'
import { useMemo, useState } from 'react'
import type { PublicStore, LayoutDSL } from '@/types/schemas'
import { LayoutDSLSchema } from '@/types/schemas'
import '@/lib/registerVariants'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { DSLSection } from './DSLSection'
import { DSLNav } from './DSLNav'
import { DSLFooter } from './DSLFooter'
import { FallbackStorefront } from './FallbackStorefront'
import { CustomCSSInjector } from './CustomCSSInjector'
import { Cart } from './Cart'
import { ProductDrawer } from './ProductDrawer'
import { useCart } from '@/lib/cart'

export function DSLRenderer({
  store, slug, preview, onOpenProduct, dslOverride, initialProductId,
}: {
  store: PublicStore
  slug: string
  preview?: boolean
  onOpenProduct?: (id: string) => void
  /** Builder injects a draft DSL without mutating the store. */
  dslOverride?: LayoutDSL | null
  /** Deep-link: open this product's drawer on mount (from ?p=). */
  initialProductId?: string | null
}) {
  const openCart = useCart((s) => s.setOpen)
  const addToCartFn = useCart((s) => s.add)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)
  const [openId, setOpenId] = useState<string | null>(initialProductId ?? null)

  // DSL-driven inline add-to-cart (no-op in preview). Opens the cart on success.
  const handleAddToCart = (id: string) => {
    if (preview) return
    void addToCartFn(id, 1).then(() => openCart(true))
  }

  // In preview mode the builder controls clicks; otherwise own the drawer.
  const handleOpen = onOpenProduct
    ?? ((id: string) => {
      setOpenId(id)
      if (!preview && typeof window !== 'undefined') {
        window.history.pushState(null, '', `/s/${slug}?p=${id}`)
      }
    })
  const openProduct = openId ? store.products.find((p) => p.id === openId) ?? null : null
  const closeDrawer = () => {
    setOpenId(null)
    if (!preview && typeof window !== 'undefined') window.history.pushState(null, '', `/s/${slug}`)
  }

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
          <Cart variant={parsed.global_config.cart_style} />
        </>
      )}
      <div data-store={slug} className={parsed.global_config.nav_style === 'sidebar-text' ? 'md:pl-44' : ''}>
        <CustomCSSInjector css={parsed.custom_css} slug={slug} />
        {!hasAnnounce && <DSLNav store={store} navStyle={parsed.global_config.nav_style} />}
        {parsed.sections.map((section, i) => (
          <DSLSection
            key={`${section.type}-${i}`}
            section={section}
            store={store}
            slug={slug}
            globalConfig={parsed.global_config}
            preview={preview}
            onOpenProduct={handleOpen}
            onAddToCart={handleAddToCart}
          />
        ))}
        <DSLFooter store={store} />
      </div>
      <ProductDrawer product={openProduct} store={store} onClose={closeDrawer} preview={preview}
                     variant={parsed.global_config.product_detail} />
    </StoreShell>
  )
}
