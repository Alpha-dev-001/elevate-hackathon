'use client'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { LayoutSection } from '@/types/schemas'
import { variantsByType } from '@/lib/dslRegistry'
import { useBuilderStore } from '@/lib/builderStore'

export function SectionCard({ section, index }: { section: LayoutSection; index: number }) {
  const id = String(index)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const updateSection = useBuilderStore((s) => s.updateSection)
  const removeSection = useBuilderStore((s) => s.removeSection)
  const variants = variantsByType(section.type)

  return (
    <div ref={setNodeRef} data-testid="section-card"
         style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
         className="flex items-center gap-2 px-3 py-2 rounded-lg"
         // eslint-disable-next-line
         data-section-type={section.type}>
      <button aria-label="Drag section" className="cursor-grab touch-none px-1 text-neutral-400" {...attributes} {...listeners}>⠿</button>
      <span className="text-xs uppercase tracking-wide w-24 text-neutral-500">{section.type.replace('_', ' ')}</span>
      <select
        data-testid="variant-select"
        value={section.variant}
        onChange={(e) => updateSection(index, { variant: e.target.value })}
        className="flex-1 text-sm bg-transparent border border-neutral-700 rounded px-2 py-1"
      >
        {variants.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
      <button aria-label="Remove section" onClick={() => removeSection(index)} className="px-2 text-neutral-400 hover:text-red-400">×</button>
    </div>
  )
}
