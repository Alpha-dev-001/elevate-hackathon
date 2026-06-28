'use client'
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter,
  useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { useBuilderStore } from '@/lib/builderStore'
import { SectionCard } from './SectionCard'

/** Pure reorder hook — exported so tests can exercise drag logic directly. */
export function applyDragEnd(activeId: string, overId: string) {
  if (activeId === overId) return
  useBuilderStore.getState().reorderSections(Number(activeId), Number(overId))
}

export function SectionList() {
  const sections = useBuilderStore((s) => s.draftDSL?.sections ?? [])
  const isDirty = useBuilderStore((s) => s.isDirty)
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const onDragEnd = (e: DragEndEvent) => {
    if (e.over) applyDragEnd(String(e.active.id), String(e.over.id))
  }

  const ids = sections.map((_, i) => String(i))

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-widest text-neutral-500">Sections</span>
        {isDirty && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400">
            Modified from Qwen&apos;s recommendation
          </span>
        )}
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {sections.map((s, i) => <SectionCard key={i} section={s} index={i} />)}
        </SortableContext>
      </DndContext>
    </div>
  )
}
