import { describe, it, expect, beforeEach } from 'vitest'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureDSL } from '@/test/fixtures'

const token: any = {
  colors: { primary: '#000', accent: '#6EE7B7', background: '#fff', surface: '#eee', text: '#000', text_muted: '#999' },
}

beforeEach(() => useBuilderStore.getState().reset())

describe('builderStore', () => {
  it('starts clean after setFromStore', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    expect(useBuilderStore.getState().isDirty).toBe(false)
  })

  it('reorderSections makes it dirty and swaps order', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().reorderSections(0, 1)
    const s = useBuilderStore.getState()
    expect(s.isDirty).toBe(true)
    expect(s.draftDSL!.sections[0].type).toBe('product_grid')
  })

  it('updateSection changes a variant', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().updateSection(0, { variant: 'minimal-wordmark' })
    expect(useBuilderStore.getState().draftDSL!.sections[0].variant).toBe('minimal-wordmark')
  })

  it('removeSection respects min 2', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().removeSection(0)
    expect(useBuilderStore.getState().draftDSL!.sections.length).toBe(2) // refused below min
  })

  it('reset reverts to original', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().updateColor('accent', '#FF0000')
    useBuilderStore.getState().reset()
    expect(useBuilderStore.getState().isDirty).toBe(false)
  })
})
