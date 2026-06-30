import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CapabilityProposals } from '@/components/terminal/CapabilityProposals'
import type { Capability } from '@/lib/api'

const proposed: Capability = {
  capability: 'mega-menu',
  label: 'mega-menu',
  count: 2,
  status: 'proposed',
  last_intent: 'make the nav a mega menu',
}
const open: Capability = {
  capability: 'video-hero',
  label: 'video hero',
  count: 1,
  status: 'open',
  last_intent: 'put a video in the hero',
}

describe('CapabilityProposals', () => {
  it('surfaces proposed capabilities with a humanized label and count', () => {
    render(<CapabilityProposals capabilities={[proposed]} />)
    const el = screen.getByTestId('capability-proposals')
    expect(el).toHaveTextContent('mega menu')          // slug humanized
    expect(el).toHaveTextContent('1 new capability')   // one proposed → singular
    expect(el).toHaveTextContent('make the nav a mega menu') // shows the wording
  })

  it('pluralizes the headline for multiple proposals', () => {
    render(
      <CapabilityProposals
        capabilities={[proposed, { ...open, status: 'proposed', count: 3 }]}
      />,
    )
    expect(screen.getByTestId('capability-proposals')).toHaveTextContent(
      '2 new capabilities',
    )
  })

  it('renders nothing when no capability has been proposed yet', () => {
    const { container } = render(<CapabilityProposals capabilities={[open]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<CapabilityProposals capabilities={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
