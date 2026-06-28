import { create } from 'zustand'
import type { LayoutDSL, LayoutSection, LayoutGlobalConfig, BrandToken, BrandColors } from '@/types/schemas'

interface BuilderStore {
  draftDSL: LayoutDSL | null
  originalDSL: LayoutDSL | null
  draftToken: BrandToken | null
  isDirty: boolean
  previewMode: boolean

  setFromStore: (dsl: LayoutDSL, token: BrandToken) => void
  updateSection: (index: number, update: Partial<LayoutSection>) => void
  reorderSections: (from: number, to: number) => void
  addSection: (section: LayoutSection) => void
  removeSection: (index: number) => void
  updateGlobalConfig: (update: Partial<LayoutGlobalConfig>) => void
  updateColor: (key: keyof BrandColors, value: string) => void
  reset: () => void
  markPublished: () => void
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

function computeDirty(draft: LayoutDSL | null, original: LayoutDSL | null, token: BrandToken | null, originalToken: BrandToken | null): boolean {
  if (!draft || !original) return false
  if (JSON.stringify(draft) !== JSON.stringify(original)) return true
  if (token && originalToken && JSON.stringify(token.colors) !== JSON.stringify(originalToken.colors)) return true
  return false
}

export const useBuilderStore = create<BuilderStore>((set, get) => {
  // Keep an immutable snapshot of the original token to diff color edits against.
  let originalToken: BrandToken | null = null

  const recompute = (partial: Partial<BuilderStore>) => {
    const next = { ...get(), ...partial }
    set({
      ...partial,
      isDirty: computeDirty(next.draftDSL, next.originalDSL, next.draftToken, originalToken),
    })
  }

  return {
    draftDSL: null,
    originalDSL: null,
    draftToken: null,
    isDirty: false,
    previewMode: false,

    setFromStore: (dsl, token) => {
      originalToken = clone(token)
      set({
        draftDSL: clone(dsl),
        originalDSL: clone(dsl),
        draftToken: clone(token),
        isDirty: false,
      })
    },

    updateSection: (index, update) => {
      const dsl = get().draftDSL
      if (!dsl) return
      const sections = dsl.sections.map((s, i) => (i === index ? { ...s, ...update } : s))
      recompute({ draftDSL: { ...dsl, sections } })
    },

    reorderSections: (from, to) => {
      const dsl = get().draftDSL
      if (!dsl) return
      const sections = [...dsl.sections]
      const [moved] = sections.splice(from, 1)
      sections.splice(to, 0, moved)
      recompute({ draftDSL: { ...dsl, sections } })
    },

    addSection: (section) => {
      const dsl = get().draftDSL
      if (!dsl || dsl.sections.length >= 5) return
      recompute({ draftDSL: { ...dsl, sections: [...dsl.sections, section] } })
    },

    removeSection: (index) => {
      const dsl = get().draftDSL
      if (!dsl || dsl.sections.length <= 2) return
      recompute({ draftDSL: { ...dsl, sections: dsl.sections.filter((_, i) => i !== index) } })
    },

    updateGlobalConfig: (update) => {
      const dsl = get().draftDSL
      if (!dsl) return
      recompute({ draftDSL: { ...dsl, global_config: { ...dsl.global_config, ...update } } })
    },

    updateColor: (key, value) => {
      const token = get().draftToken
      if (!token) return
      recompute({ draftToken: { ...token, colors: { ...token.colors, [key]: value } } })
    },

    reset: () => {
      const original = get().originalDSL
      set({
        draftDSL: original ? clone(original) : null,
        draftToken: originalToken ? clone(originalToken) : null,
        isDirty: false,
      })
    },

    markPublished: () => {
      const dsl = get().draftDSL
      originalToken = get().draftToken ? clone(get().draftToken!) : null
      set({ originalDSL: dsl ? clone(dsl) : null, isDirty: false })
    },
  }
})
