'use client'
import { useMemo, useState } from 'react'
import type { PublicStore, LayoutDSL } from '@/types/schemas'
import { LayoutDSLSchema } from '@/types/schemas'
import '@/lib/registerVariants'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { sameCategory } from '@/lib/category'
import { DSLSection } from './DSLSection'
import { DSLNav } from './DSLNav'
import { DSLFooter } from './DSLFooter'
import { FallbackStorefront } from './FallbackStorefront'
import { CustomCSSInjector } from './CustomCSSInjector'
import { Cart } from './Cart'
import { ProductDrawer } from './ProductDrawer'
import { PromoCountdown } from './PromoCountdown'
import { useCart } from '@/lib/cart'
import { useCustomer } from '@/lib/customerAuth'
import { trackProductView, trackAddToCart, markInteracted } from '@/lib/behavior'
import { useEffect } from 'react'
import { IconCart, IconUser } from '@/components/icons'

import type { EditTarget } from '@/lib/dslRegistry'

export function DSLRenderer({
  store, slug, preview, onOpenProduct, dslOverride, initialProductId, editMode, onSelectTarget,
}: {
  store: PublicStore
  slug: string
  preview?: boolean
  onOpenProduct?: (id: string) => void
  /** Builder injects a draft DSL without mutating the store. */
  dslOverride?: LayoutDSL | null
  /** Deep-link: open this product's drawer on mount (from ?p=). */
  initialProductId?: string | null
  /** Point-and-edit: when true, sections/nav become selectable in preview. */
  editMode?: boolean
  onSelectTarget?: (t: EditTarget) => void
}) {
  const openCart = useCart((s) => s.setOpen)
  const addToCartFn = useCart((s) => s.add)
  const cartCount = useCart((s) => s.cart?.item_count ?? 0)
  const customer = useCustomer((s) => s.customer)
  const initCustomer = useCustomer((s) => s.init)
  const [openId, setOpenId] = useState<string | null>(initialProductId ?? null)
  // Owned here (not in DSLNav) because filtering has to happen where
  // store.products is actually handed to the product_grid section — see
  // memory: elevate-dsl-category-filter-broken for why this used to be a
  // no-op cosmetic-only chip.
  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  // Resolve the signed-in customer for this store (guest = null). Not in preview.
  useEffect(() => {
    if (!preview) initCustomer(slug)
  }, [slug, preview, initCustomer])

  // Track product detail views when the drawer opens
  useEffect(() => {
    if (openId && !preview) {
      trackProductView(openId)
      markInteracted()
    }
  }, [openId, preview])

  // Track product card views via IntersectionObserver — fires when product cards
  // enter the viewport. Uses the [data-product] attribute present on all card variants.
  // Deduplication is handled inside trackProductView (30s window per product).
  useEffect(() => {
    if (preview || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const pid = (entry.target as HTMLElement).dataset.productId
            if (pid) {
              trackProductView(pid)
              markInteracted()
            }
          }
        })
      },
      { threshold: 0.5 } // 50% visible = "viewed"
    )
    // Observe all product cards
    const cards = document.querySelectorAll('[data-product]')
    cards.forEach((card) => observer.observe(card))
    return () => observer.disconnect()
  }, [preview, store.products])

  // DSL-driven inline add-to-cart (no-op in preview). Opens the cart on success.
  const handleAddToCart = (id: string) => {
    if (preview) return
    trackAddToCart(id)
    markInteracted()
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
    // Graceful degradation: FallbackStorefront renders a complete branded store
    // without depending on the DSL. In the builder, surface a warning so the
    // merchant knows their layout was invalid. On the live storefront, silent —
    // the customer should never see an error state.
    const fallback = <FallbackStorefront store={store} slug={slug} />
    if (preview) {
      return (
        <div className="relative h-full">
          <div className="absolute top-0 left-0 right-0 z-50 flex items-center gap-2 px-4 py-2 text-xs font-medium"
               style={{ background: 'rgba(255, 209, 102, 0.15)', color: '#FFD166', borderBottom: '1px solid rgba(255, 209, 102, 0.2)' }}>
            <span>⚠</span>
            <span>Layout validation failed — rendering safe storefront. Publish to apply your layout.</span>
          </div>
          {fallback}
        </div>
      )
    }
    return fallback
  }

  const theme = resolveTheme(store)
  const hasAnnounce = parsed.sections[0]?.variant === 'announcement-bar'
  // An active cart-recovery offer takes the top banner: it's the live nudge to
  // finish an abandoned cart. It's order-level (the browse grid stays full price)
  // so it reads as an announcement, not a store-wide sale.
  const rec = store.recovery
  const recoveryActive = !!rec && rec.percent > 0 && rec.expires_at > Date.now()
  // Promo bar is redundant when an announcement-bar section or the recovery
  // banner already leads.
  const showPromoBar = store.promos.length > 0 && !hasAnnounce && !recoveryActive

  return (
    <StoreShell brandToken={store.brand_token} cssVars={theme.cssVars}>
      {recoveryActive && rec && (
        <div className="w-full text-center py-2.5 text-sm font-semibold flex items-center justify-center gap-2 flex-wrap px-4"
             style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
          <IconCart size={16} />
          <span>{rec.label}</span>
          <PromoCountdown expiresAt={rec.expires_at} />
        </div>
      )}
      {showPromoBar && (
        <div className="w-full text-center py-2.5 text-sm font-medium flex items-center justify-center gap-2 flex-wrap px-4"
             style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}>
          <span>{store.promos[0].label}</span>
          <PromoCountdown expiresAt={store.promos[0].expires_at} />
        </div>
      )}
      {!preview && (
        <>
          <a
            href={`/s/${slug}/account`}
            aria-label={customer ? `Account: ${customer.name}` : 'Sign in'}
            className="fixed top-4 right-20 z-30 h-10 px-3 rounded-full flex items-center gap-1.5 text-sm font-medium shadow-lg hover:opacity-90 transition-opacity"
            style={{ background: 'var(--s-surface)', color: 'var(--s-text)' }}
          >
            {customer ? <IconUser size={16} /> : <span aria-hidden>↪</span>}
            <span className="hidden sm:inline">{customer ? customer.name.split(' ')[0] : 'Sign in'}</span>
          </a>
          <button
            onClick={() => openCart(true)}
            aria-label={`Open cart (${cartCount} items)`}
            className="fixed top-4 right-4 z-30 rounded-full w-12 h-12 flex items-center justify-center shadow-lg hover:opacity-90 transition-opacity"
            style={{ background: 'var(--s-cta)', color: 'var(--s-on-cta)' }}
          >
            <IconCart size={20} />
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
      <div data-store={slug} className={`relative ${parsed.global_config.nav_style === 'sidebar-text' ? 'md:pl-44' : ''}`}>
        <CustomCSSInjector css={parsed.custom_css} slug={slug} />
        {!hasAnnounce && (
          <EditTargetWrap editMode={editMode} onClick={() => onSelectTarget?.({ kind: 'global', field: 'nav_style' })} label="Navigation">
            <DSLNav
              store={store}
              navStyle={parsed.global_config.nav_style}
              preview={preview}
              activeCategory={activeCategory}
              onSelectCategory={setActiveCategory}
            />
          </EditTargetWrap>
        )}
        {parsed.sections.map((section, i) => (
          <EditTargetWrap key={`${section.type}-${i}`} editMode={editMode}
                          onClick={() => onSelectTarget?.({ kind: 'section', index: i, sectionType: section.type, variant: section.variant })}
                          label={`${section.type.replace('_', ' ')} · ${section.variant}`}>
            <DSLSection
              section={section}
              // Only the product grid should ever be scoped by the category
              // filter — a hero/banner/story section needs the full catalog
              // for its own logic (e.g. a hero's featured product lookup),
              // and must not disappear just because a customer filtered
              // elsewhere on the page.
              store={
                section.type === 'product_grid' && activeCategory
                  ? { ...store, products: store.products.filter((p) => sameCategory(p.category, activeCategory)) }
                  : store
              }
              slug={slug}
              globalConfig={parsed.global_config}
              preview={preview}
              onOpenProduct={handleOpen}
              onAddToCart={handleAddToCart}
            />
          </EditTargetWrap>
        ))}
        <DSLFooter store={store} />
      </div>
      <ProductDrawer product={openProduct} store={store} onClose={closeDrawer} preview={preview}
                     variant={parsed.global_config.product_detail} />
    </StoreShell>
  )
}

/**
 * In edit mode, wraps a storefront region so clicking it selects that DSL target
 * (point-and-edit). A hover ring + label make regions discoverable. Outside edit
 * mode it's a transparent passthrough — zero effect on the live store.
 */
function EditTargetWrap({
  editMode, onClick, label, children,
}: {
  editMode?: boolean
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  if (!editMode) return <>{children}</>
  return (
    <div
      className="relative group/edit cursor-pointer outline-2 -outline-offset-2 outline-transparent hover:outline-dashed hover:outline-[var(--color-accent,#6EE7B7)]"
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); onClick() }}
    >
      {/* Block the storefront's own interactions while editing this region. */}
      <div className="pointer-events-none">{children}</div>
      <span className="absolute top-1 left-1 z-30 px-1.5 py-0.5 rounded text-[10px] font-mono opacity-0 group-hover/edit:opacity-100 transition-opacity"
            style={{ background: 'var(--color-accent,#6EE7B7)', color: '#0A0A0B' }}>
        ✦ {label}
      </span>
    </div>
  )
}
