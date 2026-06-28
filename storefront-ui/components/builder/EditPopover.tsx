'use client'
import { useState } from 'react'
import type { EditTarget } from '@/lib/dslRegistry'
import { variantsByType, GLOBAL_OPTIONS } from '@/lib/dslRegistry'
import { useBuilderStore } from '@/lib/builderStore'

const FIELD_LABEL: Record<string, string> = {
  nav_style: 'Navigation style', product_card: 'Product card', add_to_cart: 'Add to cart',
  product_detail: 'Product detail', cart_style: 'Cart style',
}

/**
 * The point-and-edit option card. Appears when the merchant clicks a region in
 * the preview. Offers instant variant swaps (no Qwen needed) PLUS a free-text
 * "Ask Qwen" that maps intent → a DSL change (Qwen does the mapping).
 */
export function EditPopover({
  target, onClose, onAskQwen, qwenBusy, qwenSuggestion, onApplyQwen,
}: {
  target: EditTarget
  onClose: () => void
  onAskQwen: (intent: string) => void
  qwenBusy?: boolean
  qwenSuggestion?: {
    explanation: string
    apply?: () => void
    proposal?: { capability: string; proposed: boolean; count: number }
  } | null
  onApplyQwen?: () => void
}) {
  const updateSection = useBuilderStore((s) => s.updateSection)
  const updateGlobalConfig = useBuilderStore((s) => s.updateGlobalConfig)
  const dsl = useBuilderStore((s) => s.draftDSL)
  const [intent, setIntent] = useState('')

  const isSection = target.kind === 'section'
  const title = isSection ? `${target.sectionType.replace('_', ' ')} section` : FIELD_LABEL[target.field]
  const options = isSection ? variantsByType(target.sectionType) : GLOBAL_OPTIONS[target.field]
  const current = isSection
    ? dsl?.sections[target.index]?.variant
    : (dsl?.global_config as any)?.[target.field]

  const pick = (value: string) => {
    if (isSection) updateSection(target.index, { variant: value })
    else updateGlobalConfig({ [target.field]: value } as any)
  }

  return (
    <div className="fixed right-4 top-20 z-50 w-72 rounded-xl shadow-2xl border p-4 flex flex-col gap-3"
         style={{ background: '#16181D', borderColor: '#2A2A30', color: '#fff' }}>
      <header className="flex items-center justify-between">
        <span className="text-sm font-semibold capitalize">{title}</span>
        <button aria-label="Close" onClick={onClose} className="text-neutral-400 hover:text-white">×</button>
      </header>

      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] uppercase tracking-widest text-neutral-500">Choose a style</span>
        <div className="grid grid-cols-1 gap-1">
          {options.map((o) => (
            <button key={o} onClick={() => pick(o)}
                    className="text-left text-xs px-2.5 py-1.5 rounded-md border transition-colors"
                    style={current === o
                      ? { background: 'var(--color-accent,#6EE7B7)', color: '#0A0A0B', borderColor: 'transparent' }
                      : { borderColor: '#2A2A30', color: '#ddd' }}>
              {o}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-1.5 pt-1 border-t" style={{ borderColor: '#2A2A30' }}>
        <span className="text-[10px] uppercase tracking-widest text-neutral-500">Or tell Qwen what you want</span>
        <textarea value={intent} onChange={(e) => setIntent(e.target.value)} rows={2}
                  placeholder="e.g. make this feel bolder and more playful"
                  className="text-xs bg-transparent border rounded-md px-2 py-1.5 resize-none outline-none"
                  style={{ borderColor: '#2A2A30' }} />
        <button onClick={() => onAskQwen(intent)} disabled={qwenBusy || !intent.trim()}
                className="text-xs font-medium px-2.5 py-1.5 rounded-md disabled:opacity-40"
                style={{ background: 'rgba(110,231,183,0.15)', color: 'var(--color-accent,#6EE7B7)' }}>
          {qwenBusy ? '✦ Qwen is thinking…' : '✦ Ask Qwen'}
        </button>

        {qwenSuggestion && (
          <div className="mt-1 rounded-md p-2 text-xs" style={{ background: 'rgba(110,231,183,0.08)' }}>
            <p className="mb-2 text-neutral-300">{qwenSuggestion.explanation}</p>

            {qwenSuggestion.apply && (
              <button onClick={onApplyQwen}
                      className="w-full text-xs font-medium px-2 py-1.5 rounded-md"
                      style={{ background: 'var(--color-accent,#6EE7B7)', color: '#0A0A0B' }}>
                Apply Qwen&apos;s suggestion
              </button>
            )}

            {qwenSuggestion.proposal && (
              qwenSuggestion.proposal.proposed ? (
                <div data-testid="capability-proposal" className="rounded-md p-2"
                     style={{ background: 'rgba(255,209,102,0.12)', color: '#FFD166' }}>
                  <p className="font-medium mb-1">✦ Qwen proposes a new capability</p>
                  <p className="text-[11px] leading-relaxed opacity-90">
                    You&apos;ve asked for <strong>{qwenSuggestion.proposal.capability.replace(/-/g, ' ')}</strong> {qwenSuggestion.proposal.count}× —
                    Qwen recommends adding it as a store option. It&apos;s queued for your store.
                  </p>
                </div>
              ) : (
                <p data-testid="capability-noted" className="text-[11px] text-neutral-400">
                  Qwen noted this — if you ask again, it&apos;ll propose adding
                  “{qwenSuggestion.proposal.capability.replace(/-/g, ' ')}” as a new capability.
                </p>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}
