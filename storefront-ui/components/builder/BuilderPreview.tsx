'use client'
import { useMemo, useState } from 'react'
import type { PublicStore, LayoutDSL } from '@/types/schemas'
import type { EditTarget } from '@/lib/dslRegistry'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { useBuilderStore } from '@/lib/builderStore'
import { api, ApiError } from '@/lib/api'
import { EditPopover } from './EditPopover'

/**
 * Right-panel live preview. Renders DSLRenderer with the draft DSL + draft token.
 * "Edit mode" turns on point-and-edit: click any region → an option card lets the
 * merchant pick a style instantly, or ask Qwen to map free-text intent to a change.
 */
export function BuilderPreview({ store }: { store: PublicStore }) {
  const draftDSL = useBuilderStore((s) => s.draftDSL)
  const draftToken = useBuilderStore((s) => s.draftToken)
  const updateSection = useBuilderStore((s) => s.updateSection)
  const updateGlobalConfig = useBuilderStore((s) => s.updateGlobalConfig)

  const [editMode, setEditMode] = useState(false)
  const [target, setTarget] = useState<EditTarget | null>(null)
  const [qwenBusy, setQwenBusy] = useState(false)
  const [suggestion, setSuggestion] = useState<{ explanation: string; apply: () => void } | null>(null)

  const previewStore: PublicStore = useMemo(
    () => ({ ...store, brand_token: draftToken ?? store.brand_token }),
    [store, draftToken],
  )

  const selectTarget = (t: EditTarget) => { setTarget(t); setSuggestion(null) }
  const closePopover = () => { setTarget(null); setSuggestion(null) }

  const askQwen = async (intent: string) => {
    if (!target || !draftDSL) return
    setQwenBusy(true)
    setSuggestion(null)
    try {
      const res = await api.editIntent(store.slug, { target, intent, dsl: draftDSL })
      const patch = res.patch
      const apply = () => {
        if (patch.kind === 'section') updateSection(patch.index, { variant: patch.variant })
        else updateGlobalConfig({ [patch.field]: patch.value } as any)
        closePopover()
      }
      setSuggestion({ explanation: res.explanation, apply })
    } catch (e) {
      setSuggestion({
        explanation: e instanceof ApiError ? `Qwen couldn't map that: ${e.message}` : 'Qwen is unavailable right now.',
        apply: () => {},
      })
    } finally {
      setQwenBusy(false)
    }
  }

  return (
    <div className="flex-1 h-full overflow-y-auto relative" style={{ transform: 'translateZ(0)' }}>
      <div className="sticky top-0 z-10 px-4 py-2 flex items-center justify-between text-[11px] uppercase tracking-widest text-neutral-400"
           style={{ background: 'rgba(10,10,11,0.8)', backdropFilter: 'blur(8px)' }}>
        <span>You are previewing</span>
        <button
          onClick={() => { setEditMode((v) => !v); closePopover() }}
          className="text-[10px] px-2 py-1 rounded-md normal-case tracking-normal font-medium"
          style={editMode
            ? { background: 'var(--color-accent,#6EE7B7)', color: '#0A0A0B' }
            : { border: '1px solid #2A2A30', color: '#aaa' }}>
          {editMode ? '✦ Editing — click any part' : 'Edit on canvas'}
        </button>
      </div>

      <DSLRenderer store={previewStore} slug={store.slug} preview dslOverride={draftDSL}
                   editMode={editMode} onSelectTarget={selectTarget} />

      {target && (
        <EditPopover
          target={target}
          onClose={closePopover}
          onAskQwen={askQwen}
          qwenBusy={qwenBusy}
          qwenSuggestion={suggestion}
          onApplyQwen={() => suggestion?.apply()}
        />
      )}
    </div>
  )
}
