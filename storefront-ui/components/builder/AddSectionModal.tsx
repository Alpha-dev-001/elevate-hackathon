'use client'
import { variantsByType } from '@/lib/dslRegistry'
import { useBuilderStore } from '@/lib/builderStore'
import type { LayoutSection } from '@/types/schemas'

const TYPES: LayoutSection['type'][] = ['hero', 'product_grid', 'banner', 'story']

export function AddSectionModal({ onClose }: { onClose: () => void }) {
  const addSection = useBuilderStore((s) => s.addSection)
  const atMax = useBuilderStore((s) => (s.draftDSL?.sections.length ?? 0) >= 5)

  const add = (type: LayoutSection['type']) => {
    const variant = variantsByType(type)[0]
    if (variant) addSection({ type, variant, props: {} })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-neutral-900 rounded-xl p-5 w-[320px]" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm uppercase tracking-widest text-neutral-400 mb-3">Add a section</h3>
        {atMax && <p className="text-xs text-amber-400 mb-2">Maximum of 5 sections reached.</p>}
        <div className="grid grid-cols-2 gap-2">
          {TYPES.map((t) => (
            <button key={t} disabled={atMax} onClick={() => add(t)}
                    className="px-3 py-2 text-sm rounded-lg border border-neutral-700 hover:border-emerald-400 disabled:opacity-40 capitalize">
              {t.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
