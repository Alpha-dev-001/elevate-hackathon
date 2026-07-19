import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OptionCard } from '@/components/terminal/OptionCard'
import type { AgentAction } from '@/types/schemas'

vi.mock('@/lib/api', () => ({
  api: {
    approveAction: vi.fn().mockResolvedValue({ action: {} }),
    dismissAction: vi.fn().mockResolvedValue({ action: {} }),
  },
}))

function makeAction(overrides: Partial<AgentAction> = {}): AgentAction {
  return {
    id: 'act_1', merchant_id: 'm1', promo_id: 'promo_1',
    action_type: 'flash_sale', trigger: 'spike', title: 'Flash Sale: 20% off Widget',
    description: 'desc', estimated_gmv: 100, estimated_confidence: 0.75,
    payload: { product_id: 'p1', discount_percent: 20 },
    brand_check: 'Aligned with warm voice', constraint_check: '', reasoning: '',
    status: 'pending', created_at: Date.now(),
    ...overrides,
  }
}

describe('OptionCard — constraint_check', () => {
  it('renders the constraint check line when present', () => {
    render(<OptionCard action={makeAction({ constraint_check: '60% exceeds your 40% discount ceiling. Clamped to 40%.' })}
      onApprove={vi.fn()} onDismiss={vi.fn()} onClamped={vi.fn()} />)
    expect(screen.getByText(/Constraint check:/)).toBeInTheDocument()
    expect(screen.getByText(/Clamped to 40%/)).toBeInTheDocument()
  })

  it('renders nothing when constraint_check is empty', () => {
    render(<OptionCard action={makeAction({ constraint_check: '' })}
      onApprove={vi.fn()} onDismiss={vi.fn()} onClamped={vi.fn()} />)
    expect(screen.queryByText(/Constraint check:/)).toBeNull()
  })
})
