'use client'
import type { LayoutSection, LayoutGlobalConfig, PublicStore } from '@/types/schemas'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'

export function DSLSection({
  section, store, slug, globalConfig, preview, onOpenProduct, onAddToCart,
}: {
  section: LayoutSection
  store: PublicStore
  slug: string
  globalConfig: LayoutGlobalConfig
  preview?: boolean
  onOpenProduct?: (id: string) => void
  onAddToCart?: (id: string) => void
}) {
  const Comp = SECTION_REGISTRY[section.type]?.[section.variant]
  return (
    <div data-dsl-section data-section-type={section.type} data-variant={section.variant}>
      {Comp ? (
        <Comp
          store={store}
          slug={slug}
          variant={section.variant}
          globalConfig={globalConfig}
          preview={preview}
          onOpenProduct={onOpenProduct}
          onAddToCart={onAddToCart}
          props={section.props}
        />
      ) : null}
    </div>
  )
}
