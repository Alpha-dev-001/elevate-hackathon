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
import { useCustomer } from '@/lib/customerAuth'
import { useEffect } from 'react'

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

  // Resolve the signed-in customer for this store (guest = null). Not in preview.
  useEffect(() => {
    if (!preview) initCustomer(slug)
  }, [slug, preview, initCustomer])

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
          <a
            href={`/s/${slug}/account`}
            aria-label={customer ? `Account: ${customer.name}` : 'Sign in'}
            className="fixed top-4 right-20 z-30 h-10 px-3 rounded-full flex items-center gap-1.5 text-sm font-medium shadow-lg hover:opacity-90 transition-opacity"
            style={{ background: 'var(--s-surface)', color: 'var(--s-text)' }}
          >
            <span aria-hidden>{customer ? '👤' : '↪'}</span>
            <span className="hidden sm:inline">{customer ? customer.name.split(' ')[0] : 'Sign in'}</span>
          </a>
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
      <div data-store={slug} className={`relative ${parsed.global_config.nav_style === 'sidebar-text' ? 'md:pl-44' : ''}`}>
        <CustomCSSInjector css={parsed.custom_css} slug={slug} />
        {!hasAnnounce && (
          <EditTargetWrap editMode={editMode} onClick={() => onSelectTarget?.({ kind: 'global', field: 'nav_style' })} label="Navigation">
            <DSLNav store={store} navStyle={parsed.global_config.nav_style} preview={preview} />
          </EditTargetWrap>
        )}
        {parsed.sections.map((section, i) => (
          <EditTargetWrap key={`${section.type}-${i}`} editMode={editMode}
                          onClick={() => onSelectTarget?.({ kind: 'section', index: i, sectionType: section.type, variant: section.variant })}
                          label={`${section.type.replace('_', ' ')} · ${section.variant}`}>
            <DSLSection
              section={section}
              store={store}
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
