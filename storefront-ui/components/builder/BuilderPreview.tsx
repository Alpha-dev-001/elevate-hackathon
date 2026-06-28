'use client'
import { useMemo } from 'react'
import type { PublicStore } from '@/types/schemas'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { useBuilderStore } from '@/lib/builderStore'

/**
 * Right-panel live preview. Renders DSLRenderer with the draft DSL + draft
 * token merged onto the base store. preview=true disables cart/checkout and the
 * drawer's URL writes. Re-renders instantly on any builder state change.
 */
export function BuilderPreview({ store }: { store: PublicStore }) {
  const draftDSL = useBuilderStore((s) => s.draftDSL)
  const draftToken = useBuilderStore((s) => s.draftToken)

  const previewStore: PublicStore = useMemo(
    () => ({
      ...store,
      brand_token: draftToken ?? store.brand_token,
    }),
    [store, draftToken],
  )

  return (
    <div className="flex-1 h-full overflow-y-auto relative">
      <div className="sticky top-0 z-10 px-4 py-2 text-[11px] uppercase tracking-widest text-neutral-400"
           style={{ background: 'rgba(10,10,11,0.8)', backdropFilter: 'blur(8px)' }}>
        You are previewing
      </div>
      <DSLRenderer store={previewStore} slug={store.slug} preview dslOverride={draftDSL} />
    </div>
  )
}
