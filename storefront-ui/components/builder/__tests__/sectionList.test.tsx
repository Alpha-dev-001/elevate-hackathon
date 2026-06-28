import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SectionList, applyDragEnd } from '@/components/builder/SectionList'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureDSL } from '@/test/fixtures'
import '@/lib/registerVariants'

const token: any = { colors: { primary: '#000', accent: '#6EE7B7', background: '#fff', surface: '#eee', text: '#000', text_muted: '#999' } }

beforeEach(() => {
  useBuilderStore.getState().reset()
  useBuilderStore.getState().setFromStore(
    { ...fixtureDSL, sections: [...fixtureDSL.sections, { type: 'story', variant: 'quote-callout', props: {} }] },
    token,
  )
})

describe('SectionList', () => {
  it('renders one card per draft section', () => {
    render(<SectionList />)
    expect(screen.getAllByTestId('section-card').length).toBe(3)
  })

  it('variant select lists that type variants and updates on change', async () => {
    render(<SectionList />)
    const select = screen.getAllByTestId('variant-select')[0] as HTMLSelectElement
    await userEvent.selectOptions(select, 'minimal-wordmark')
    expect(useBuilderStore.getState().draftDSL!.sections[0].variant).toBe('minimal-wordmark')
  })

  it('remove reduces a 3-section draft to 2', async () => {
    render(<SectionList />)
    await userEvent.click(screen.getAllByLabelText('Remove section')[0])
    expect(useBuilderStore.getState().draftDSL!.sections.length).toBe(2)
  })

  it('applyDragEnd reorders via the store', () => {
    applyDragEnd('0', '2')
    expect(useBuilderStore.getState().draftDSL!.sections[2].type).toBe('hero')
    expect(useBuilderStore.getState().isDirty).toBe(true)
  })
})
