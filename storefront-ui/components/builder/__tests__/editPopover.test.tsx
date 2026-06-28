import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditPopover } from '@/components/builder/EditPopover'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureDSL, fixtureStore } from '@/test/fixtures'
import '@/lib/registerVariants'

beforeEach(() => {
  useBuilderStore.getState().reset()
  useBuilderStore.getState().setFromStore(fixtureDSL, fixtureStore.brand_token!)
})

describe('EditPopover (point-and-edit)', () => {
  it('instant variant pick updates the targeted section', async () => {
    render(<EditPopover target={{ kind: 'section', index: 0, sectionType: 'hero', variant: 'editorial-stacked' }}
                        onClose={() => {}} onAskQwen={() => {}} />)
    await userEvent.click(screen.getByText('minimal-wordmark'))
    expect(useBuilderStore.getState().draftDSL!.sections[0].variant).toBe('minimal-wordmark')
  })

  it('global field pick updates global_config', async () => {
    render(<EditPopover target={{ kind: 'global', field: 'nav_style' }}
                        onClose={() => {}} onAskQwen={() => {}} />)
    await userEvent.click(screen.getByText('pill-nav'))
    expect(useBuilderStore.getState().draftDSL!.global_config.nav_style).toBe('pill-nav')
  })

  it('Ask Qwen fires with the typed intent', async () => {
    const ask = vi.fn()
    render(<EditPopover target={{ kind: 'global', field: 'nav_style' }} onClose={() => {}} onAskQwen={ask} />)
    await userEvent.type(screen.getByPlaceholderText(/bolder/i), 'make it minimal')
    await userEvent.click(screen.getByText('✦ Ask Qwen'))
    expect(ask).toHaveBeenCalledWith('make it minimal')
  })

  it('shows a capability proposal once an unmet intent recurs', () => {
    render(<EditPopover target={{ kind: 'global', field: 'nav_style' }} onClose={() => {}} onAskQwen={() => {}}
                        qwenSuggestion={{ explanation: 'No nav option does that.', proposal: { capability: 'mega-menu', proposed: true, count: 2 } }} />)
    expect(screen.getByTestId('capability-proposal')).toHaveTextContent('mega menu')
  })

  it('just notes a first-time unmet intent', () => {
    render(<EditPopover target={{ kind: 'global', field: 'nav_style' }} onClose={() => {}} onAskQwen={() => {}}
                        qwenSuggestion={{ explanation: 'No nav option does that.', proposal: { capability: 'mega-menu', proposed: false, count: 1 } }} />)
    expect(screen.getByTestId('capability-noted')).toBeTruthy()
    expect(screen.queryByTestId('capability-proposal')).toBeFalsy()
  })
})
