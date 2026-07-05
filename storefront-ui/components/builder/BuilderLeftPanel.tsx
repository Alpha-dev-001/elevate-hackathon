'use client'
import { useState } from 'react'
import type { BrandGuardRules, BrandLayoutToken, LayoutGlobalConfig } from '@/types/schemas'
import { useBuilderStore } from '@/lib/builderStore'
import { SectionList } from './SectionList'
import { AddSectionModal } from './AddSectionModal'
import { ColorPicker } from './ColorPicker'

// Layout presets swap global_config instantly (a "Regenerate with Qwen" button
// in the page does the network round-trip — Task 20/21).
const LAYOUT_PRESETS: Record<BrandLayoutToken['style'], Partial<LayoutGlobalConfig>> = {
  editorial: { nav_style: 'underline-tabs', product_card: 'editorial-horizontal', corner_radius: 'sm', density: 'normal' },
  'bold-grid': { nav_style: 'pill-nav', product_card: 'colored-bg-card', corner_radius: 'lg', density: 'dense' },
  'minimal-dark': { nav_style: 'sidebar-text', product_card: 'hover-reveal-text', corner_radius: 'none', density: 'sparse' },
  'warm-craft': { nav_style: 'pill-nav', product_card: 'polaroid-card', corner_radius: 'md', density: 'normal' },
}

export function BuilderLeftPanel({
  guards, onPublish, onRegenerate, publishing,
}: {
  guards: BrandGuardRules | null
  onPublish: () => void
  onRegenerate: () => void
  publishing?: boolean
}) {
  const [adding, setAdding] = useState(false)
  const [advisoryMode, setAdvisoryMode] = useState<'conversational' | 'structured'>('conversational')
  const isDirty = useBuilderStore((s) => s.isDirty)
  const updateGlobalConfig = useBuilderStore((s) => s.updateGlobalConfig)
  const gc = useBuilderStore((s) => s.draftDSL?.global_config)
  const reset = useBuilderStore((s) => s.reset)

  return (
    <aside className="w-[320px] shrink-0 h-full overflow-y-auto border-r border-neutral-800 p-4 flex flex-col gap-5"
           style={{ background: 'var(--color-surface, #111113)' }}>
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Your Store</h2>
        {!isDirty && <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400">✦ Qwen Recommended</span>}
      </header>

      <section>
        <span className="text-xs uppercase tracking-widest text-neutral-500">Layout</span>
        <div className="grid grid-cols-2 gap-2 mt-2">
          {(Object.keys(LAYOUT_PRESETS) as BrandLayoutToken['style'][]).map((style) => (
            <button key={style} onClick={() => updateGlobalConfig(LAYOUT_PRESETS[style])}
                    className="px-3 py-2 text-xs rounded-lg border border-neutral-700 hover:border-emerald-400 capitalize">
              {style.replace('-', ' ')}
            </button>
          ))}
        </div>
      </section>

      <SectionList />
      <button onClick={() => setAdding(true)} className="text-sm text-emerald-400 text-left">+ Add Section</button>
      {adding && <AddSectionModal onClose={() => setAdding(false)} />}

      <section className="flex flex-col gap-3">
        <span className="text-xs uppercase tracking-widest text-neutral-500">Colors</span>
        <ColorPicker colorKey="primary" guards={guards} advisoryMode={advisoryMode} />
        <ColorPicker colorKey="accent" guards={guards} advisoryMode={advisoryMode} />
        <ColorPicker colorKey="background" guards={guards} advisoryMode={advisoryMode} />
      </section>

      <section className="flex flex-col gap-3">
        <span className="text-xs uppercase tracking-widest text-neutral-500">Store behavior</span>
        <ConfigSelect label="Add to cart" value={gc?.add_to_cart ?? 'drawer-only'}
                      options={['drawer-only', 'card-hover', 'card-always', 'none']}
                      onChange={(v) => updateGlobalConfig({ add_to_cart: v as LayoutGlobalConfig['add_to_cart'] })} />
        <ConfigSelect label="Product detail" value={gc?.product_detail ?? 'gallery-split'}
                      options={['gallery-split', 'editorial-stacked', 'minimal-centered']}
                      onChange={(v) => updateGlobalConfig({ product_detail: v as LayoutGlobalConfig['product_detail'] })} />
        <ConfigSelect label="Cart" value={gc?.cart_style ?? 'slide-panel'}
                      options={['slide-panel', 'full-sheet']}
                      onChange={(v) => updateGlobalConfig({ cart_style: v as LayoutGlobalConfig['cart_style'] })} />
      </section>

      <section>
        <span className="text-xs uppercase tracking-widest text-neutral-500">Advisory style</span>
        <div className="flex gap-2 mt-2">
          {(['conversational', 'structured'] as const).map((m) => (
            <button key={m} onClick={() => setAdvisoryMode(m)}
                    className="px-3 py-1 text-xs rounded-full border capitalize"
                    style={{ borderColor: advisoryMode === m ? 'var(--color-accent,#6EE7B7)' : '#333' }}>
              {m}
            </button>
          ))}
        </div>
      </section>

      <button onClick={onRegenerate} className="text-xs text-neutral-400 text-left hover:text-emerald-400">
        ✦ Regenerate with Qwen
      </button>

      <footer className="mt-auto flex flex-col gap-2 pt-4">
        {isDirty && (
          <button onClick={reset}
                  className="w-full py-2 rounded-lg text-xs font-medium border border-neutral-600 text-neutral-200 transition-colors hover:border-emerald-400 hover:text-emerald-400">
            ↺ Restore Qwen&apos;s original
          </button>
        )}
        <button onClick={onPublish} disabled={publishing}
                className="w-full py-2.5 rounded-lg font-medium disabled:opacity-50"
                style={{ background: 'var(--color-accent,#6EE7B7)', color: '#0A0A0B' }}>
          {publishing ? 'Publishing…' : 'Publish Store →'}
        </button>
      </footer>
    </aside>
  )
}

function ConfigSelect({
  label, value, options, onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-neutral-400">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="text-xs border border-neutral-700 rounded px-2 py-1 max-w-[60%]"
        style={{ background: '#16181D', color: '#e5e5e5' }}
      >
        {options.map((o) => <option key={o} value={o} style={{ background: '#16181D', color: '#fff' }}>{o}</option>)}
      </select>
    </label>
  )
}
